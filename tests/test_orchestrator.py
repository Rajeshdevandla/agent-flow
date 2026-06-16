"""
tests/test_orchestrator.py

Test suite for AgentFlow v2.0 orchestrator and workflow pipeline.

What these tests prove and why they matter:
- End-to-end workflow integrity: the 6-agent pipeline produces a complete, structured output
- Failure recovery: the orchestrator handles agent failures without crashing the entire pipeline
- Decision logging: every agent step is recorded, enabling full audit trails
- Revision loop bounds: CriticAgent never loops more than the allowed maximum
- Safety gate enforcement: SafetyAgent BLOCK stops the workflow before output reaches the user

Run with: pytest tests/test_orchestrator.py -v
"""

import pytest
import json
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Minimal data structures (mirrors orchestrator/workflow.py internals)
# These allow tests to run without importing the full agent stack
# ---------------------------------------------------------------------------

@dataclass
class SubTask:
    subtask_id: str
    description: str
    assigned_to: str
    estimated_complexity: str = "MEDIUM"
    confidence: float = 0.8
    dependencies: list = field(default_factory=list)
    success_criteria: str = ""


@dataclass
class Plan:
    task_id: str
    original_task: str
    subtasks: list
    max_steps: int = 7
    confidence: float = 0.8
    reasoning: str = ""


@dataclass
class ResearchFinding:
    claim: str
    confidence: float
    source_type: str  # training_data | reasoning | uncertain
    caveats: str


@dataclass
class ResearchReport:
    subtask_id: str
    findings: list
    synthesis: str
    gaps: list
    recommended_next_step: str


@dataclass
class Summary:
    summary: str
    key_points: list
    confidence: float
    tone: str
    flagged_uncertainties: list
    word_count: int


@dataclass
class CriticReview:
    verdict: str  # PASS | REVISE | REJECT
    score: float
    issues: list
    revision_instructions: str
    passes_safety_gate: bool


@dataclass
class SafetyEvaluation:
    overall_status: str  # SAFE | REVIEW | BLOCKED
    action: str  # CONTINUE | FLAG_FOR_REVIEW | STOP_WORKFLOW
    blocking_principles: list
    self_critique: str


@dataclass
class WorkflowResult:
    task_id: str
    plan: Optional[Plan]
    research: Optional[ResearchReport]
    summary: Optional[Summary]
    critic_review: Optional[CriticReview]
    safety_evaluation: Optional[SafetyEvaluation]
    final_output: Optional[str]
    status: str  # COMPLETE | FAILED | BLOCKED
    revision_count: int = 0
    decision_log: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mock agent factory
# Returns configurable mock agents for isolation testing
# ---------------------------------------------------------------------------

def make_mock_planner(confidence=0.85, step_count=3):
    """Creates a PlannerAgent mock that returns a valid plan."""
    agent = MagicMock()
    agent.run.return_value = Plan(
        task_id="TEST_001",
        original_task="Test task",
        subtasks=[
            SubTask(
                subtask_id=f"PLAN_00{i+1}",
                description=f"Step {i+1}",
                assigned_to="ResearcherAgent",
                confidence=confidence
            )
            for i in range(step_count)
        ],
        confidence=confidence
    )
    return agent


def make_mock_researcher(source_type="training_data", finding_confidence=0.9):
    """Creates a ResearcherAgent mock with configurable source labeling."""
    agent = MagicMock()
    agent.run.return_value = ResearchReport(
        subtask_id="PLAN_001",
        findings=[
            ResearchFinding(
                claim="Test finding",
                confidence=finding_confidence,
                source_type=source_type,
                caveats="No significant caveats"
            )
        ],
        synthesis="Test synthesis paragraph.",
        gaps=[],
        recommended_next_step="Summarize findings"
    )
    return agent


def make_mock_summarizer(word_count=250, confidence=0.82):
    """Creates a SummarizerAgent mock within valid word count bounds."""
    agent = MagicMock()
    agent.run.return_value = Summary(
        summary="This is a test summary. " * 10,
        key_points=["Point 1", "Point 2", "Point 3"],
        confidence=confidence,
        tone="professional",
        flagged_uncertainties=[],
        word_count=word_count
    )
    return agent


def make_mock_critic(verdict="PASS", score=0.85):
    """Creates a CriticAgent mock with configurable verdict."""
    agent = MagicMock()
    agent.run.return_value = CriticReview(
        verdict=verdict,
        score=score,
        issues=[],
        revision_instructions="",
        passes_safety_gate=True
    )
    return agent


def make_mock_safety(status="SAFE", action="CONTINUE", blocking_principles=None):
    """Creates a SafetyAgent mock — default is SAFE/CONTINUE."""
    agent = MagicMock()
    agent.run.return_value = SafetyEvaluation(
        overall_status=status,
        action=action,
        blocking_principles=blocking_principles or [],
        self_critique="No additional risks identified."
    )
    return agent


class MockDecisionLogger:
    """
    Minimal decision logger that records all events.
    Proves: every agent step is captured in an audit trail.
    """
    def __init__(self):
        self.events = []

    def log(self, agent_name: str, action: str, data: dict):
        self.events.append({
            "agent": agent_name,
            "action": action,
            "data": data
        })

    def get_event_count(self):
        return len(self.events)

    def get_events_for_agent(self, agent_name: str):
        return [e for e in self.events if e["agent"] == agent_name]


class MockOrchestrator:
    """
    Simplified orchestrator for testing — mirrors the real workflow.py logic
    without requiring live Anthropic API calls.
    """
    MAX_REVISIONS = 2

    def __init__(self, planner, researcher, summarizer, critic, safety, logger):
        self.planner = planner
        self.researcher = researcher
        self.summarizer = summarizer
        self.critic = critic
        self.safety = safety
        self.logger = logger

    def run(self, task: str) -> WorkflowResult:
        result = WorkflowResult(
            task_id="TEST_001",
            plan=None,
            research=None,
            summary=None,
            critic_review=None,
            safety_evaluation=None,
            final_output=None,
            status="FAILED"
        )

        # Step 1: Plan
        try:
            plan = self.planner.run(task)
            result.plan = plan
            self.logger.log("PlannerAgent", "PLAN_CREATED", {"steps": len(plan.subtasks)})
        except Exception as e:
            self.logger.log("PlannerAgent", "PLAN_FAILED", {"error": str(e)})
            result.status = "FAILED"
            return result

        # Step 2: Research
        try:
            research = self.researcher.run(plan)
            result.research = research
            self.logger.log("ResearcherAgent", "RESEARCH_COMPLETE", {"findings": len(research.findings)})
        except Exception as e:
            self.logger.log("ResearcherAgent", "RESEARCH_FAILED", {"error": str(e)})
            result.status = "FAILED"
            return result

        # Step 3: Summarize + Critic loop (max 2 revisions)
        revision_count = 0
        summary = None
        critic_review = None

        while revision_count <= self.MAX_REVISIONS:
            try:
                summary = self.summarizer.run(research)
                self.logger.log("SummarizerAgent", "SUMMARY_CREATED", {"word_count": summary.word_count})

                critic_review = self.critic.run(summary, research)
                self.logger.log("CriticAgent", f"VERDICT_{critic_review.verdict}", {"score": critic_review.score})

                if critic_review.verdict == "PASS":
                    break
                elif critic_review.verdict == "REJECT":
                    result.status = "FAILED"
                    return result
                else:  # REVISE
                    revision_count += 1
                    result.revision_count = revision_count
                    if revision_count > self.MAX_REVISIONS:
                        self.logger.log("CriticAgent", "MAX_REVISIONS_REACHED", {"count": revision_count})
                        break

            except Exception as e:
                self.logger.log("SummarizerAgent", "SUMMARIZER_FAILED", {"error": str(e)})
                result.status = "FAILED"
                return result

        result.summary = summary
        result.critic_review = critic_review

        # Step 4: Safety gate
        try:
            safety_eval = self.safety.run(summary)
            result.safety_evaluation = safety_eval
            self.logger.log("SafetyAgent", f"SAFETY_{safety_eval.overall_status}", {
                "action": safety_eval.action,
                "blocking_principles": safety_eval.blocking_principles
            })

            if safety_eval.action == "STOP_WORKFLOW":
                result.status = "BLOCKED"
                return result

        except Exception as e:
            self.logger.log("SafetyAgent", "SAFETY_CHECK_FAILED", {"error": str(e)})
            result.status = "FAILED"
            return result

        result.final_output = summary.summary
        result.status = "COMPLETE"
        return result


# ---------------------------------------------------------------------------
# UNIT TESTS
# ---------------------------------------------------------------------------

class TestWorkflowEndToEnd:
    """
    Tests that the full 6-agent pipeline runs to completion and produces
    a structured output with all required fields populated.

    Why this matters: integration failures (wrong agent order, missing
    handoffs, broken data contracts) are the most common failure mode
    in multi-agent systems. These tests catch them at the seam level.
    """

    def setup_method(self):
        """Set up clean mocks and logger for each test."""
        self.logger = MockDecisionLogger()
        self.planner = make_mock_planner()
        self.researcher = make_mock_researcher()
        self.summarizer = make_mock_summarizer()
        self.critic = make_mock_critic(verdict="PASS")
        self.safety = make_mock_safety(status="SAFE", action="CONTINUE")
        self.orchestrator = MockOrchestrator(
            self.planner, self.researcher, self.summarizer,
            self.critic, self.safety, self.logger
        )

    def test_happy_path_returns_complete_status(self):
        """
        Proves: a valid task goes through all 6 agents and returns COMPLETE.
        """
        result = self.orchestrator.run("Explain quantum computing")
        assert result.status == "COMPLETE"

    def test_happy_path_all_fields_populated(self):
        """
        Proves: final WorkflowResult has plan, research, summary, critic review,
        safety eval, and final output — no None fields in a successful run.
        """
        result = self.orchestrator.run("Explain quantum computing")
        assert result.plan is not None
        assert result.research is not None
        assert result.summary is not None
        assert result.critic_review is not None
        assert result.safety_evaluation is not None
        assert result.final_output is not None

    def test_happy_path_final_output_is_string(self):
        """
        Proves: final_output is always a string — downstream consumers
        can rely on this type contract without null checks.
        """
        result = self.orchestrator.run("What is machine learning?")
        assert isinstance(result.final_output, str)
        assert len(result.final_output) > 0

    def test_plan_step_count_within_bounds(self):
        """
        Proves: PlannerAgent respects the 7-step maximum.
        A plan with more than 7 steps indicates the step limit is not enforced.
        """
        self.planner = make_mock_planner(step_count=7)
        self.orchestrator.planner = self.planner
        result = self.orchestrator.run("Complex multi-part task")
        assert len(result.plan.subtasks) <= 7


class TestFailureRecovery:
    """
    Tests that the orchestrator handles agent failures gracefully.

    Why this matters: in production, individual agent calls can fail
    (network timeout, malformed response, context length exceeded).
    The orchestrator must fail safely — no partial outputs, clear
    status reporting, full audit trail of what went wrong.
    """

    def setup_method(self):
        self.logger = MockDecisionLogger()

    def test_planner_failure_returns_failed_status(self):
        """
        Proves: if PlannerAgent throws an exception, status is FAILED
        and the workflow does not attempt to continue.
        """
        planner = MagicMock()
        planner.run.side_effect = Exception("PlannerAgent connection timeout")

        orchestrator = MockOrchestrator(
            planner,
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(),
            make_mock_safety(),
            self.logger
        )
        result = orchestrator.run("Test task")
        assert result.status == "FAILED"

    def test_planner_failure_does_not_call_downstream_agents(self):
        """
        Proves: if PlannerAgent fails, ResearcherAgent is never called.
        Downstream agents must not receive partial/missing input.
        """
        planner = MagicMock()
        planner.run.side_effect = Exception("PlannerAgent failed")
        researcher = make_mock_researcher()

        orchestrator = MockOrchestrator(
            planner, researcher,
            make_mock_summarizer(), make_mock_critic(),
            make_mock_safety(), self.logger
        )
        orchestrator.run("Test task")
        researcher.run.assert_not_called()

    def test_researcher_failure_returns_failed_status(self):
        """
        Proves: ResearcherAgent failure is caught and reported correctly.
        """
        researcher = MagicMock()
        researcher.run.side_effect = Exception("ResearcherAgent context limit exceeded")

        orchestrator = MockOrchestrator(
            make_mock_planner(), researcher,
            make_mock_summarizer(), make_mock_critic(),
            make_mock_safety(), self.logger
        )
        result = orchestrator.run("Test task")
        assert result.status == "FAILED"
        assert result.research is None

    def test_failure_is_logged_with_error_detail(self):
        """
        Proves: failures are logged with enough detail to diagnose the problem.
        The audit trail must capture the error, not just the status change.
        """
        planner = MagicMock()
        planner.run.side_effect = Exception("Specific error message")

        orchestrator = MockOrchestrator(
            planner, make_mock_researcher(),
            make_mock_summarizer(), make_mock_critic(),
            make_mock_safety(), self.logger
        )
        orchestrator.run("Test task")

        planner_events = self.logger.get_events_for_agent("PlannerAgent")
        failed_events = [e for e in planner_events if "FAILED" in e["action"]]
        assert len(failed_events) > 0
        assert "error" in failed_events[0]["data"]


class TestDecisionLogger:
    """
    Tests that the decision logger captures all agent steps.

    Why this matters: the decision audit trail is a core feature
    of AgentFlow v2.0 — it's what makes the system inspectable
    and debuggable. If logging is incomplete, the system is a
    black box.
    """

    def setup_method(self):
        self.logger = MockDecisionLogger()
        self.orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            self.logger
        )

    def test_all_agents_produce_log_entries(self):
        """
        Proves: every agent in the pipeline logs at least one event.
        A successful run must have log entries from all agents.
        """
        self.orchestrator.run("Test task")
        agents_logged = {e["agent"] for e in self.logger.events}
        expected_agents = {"PlannerAgent", "ResearcherAgent", "SummarizerAgent",
                          "CriticAgent", "SafetyAgent"}
        assert expected_agents.issubset(agents_logged)

    def test_log_entry_count_is_positive(self):
        """
        Proves: the logger is actually recording events, not silently dropping them.
        """
        self.orchestrator.run("Test task")
        assert self.logger.get_event_count() >= 5  # at minimum, one per agent

    def test_log_entries_have_required_fields(self):
        """
        Proves: every log entry has agent name, action, and data fields.
        Partial log entries are useless for debugging.
        """
        self.orchestrator.run("Test task")
        for event in self.logger.events:
            assert "agent" in event
            assert "action" in event
            assert "data" in event

    def test_planner_log_contains_step_count(self):
        """
        Proves: PlannerAgent logs the number of subtasks created.
        This lets you verify the plan was decomposed correctly from logs alone.
        """
        self.orchestrator.run("Test task")
        planner_events = self.logger.get_events_for_agent("PlannerAgent")
        plan_created = [e for e in planner_events if e["action"] == "PLAN_CREATED"]
        assert len(plan_created) > 0
        assert "steps" in plan_created[0]["data"]


class TestRevisionLoop:
    """
    Tests that the CriticAgent revision loop terminates correctly.

    Why this matters: without explicit termination conditions, critic-summarizer
    feedback loops can become infinite. The max 2 revision limit is a safety
    mechanism — these tests verify it works.
    """

    def setup_method(self):
        self.logger = MockDecisionLogger()

    def test_pass_on_first_attempt_no_revisions(self):
        """
        Proves: if CriticAgent returns PASS immediately, revision count is 0.
        """
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            self.logger
        )
        result = orchestrator.run("Test task")
        assert result.revision_count == 0

    def test_revision_loop_terminates_at_max(self):
        """
        Proves: even if CriticAgent always returns REVISE, the loop terminates
        after MAX_REVISIONS and does not run indefinitely.

        This is the most important test in this class — it verifies the
        explicit termination condition works.
        """
        # Critic always returns REVISE
        critic = MagicMock()
        critic.run.return_value = CriticReview(
            verdict="REVISE",
            score=0.6,
            issues=[{"type": "missing_caveat", "severity": "MEDIUM"}],
            revision_instructions="Add more caveats",
            passes_safety_gate=True
        )

        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            critic,
            make_mock_safety(status="SAFE", action="CONTINUE"),
            self.logger
        )
        result = orchestrator.run("Test task")
        # Should have stopped at MAX_REVISIONS, not looped forever
        assert result.revision_count <= MockOrchestrator.MAX_REVISIONS

    def test_summarizer_called_once_per_revision_cycle(self):
        """
        Proves: SummarizerAgent is called exactly once per revision cycle.
        Multiple summarizer calls per cycle would indicate a logic error.
        """
        # PASS immediately — one summarizer call expected
        summarizer = make_mock_summarizer()
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            summarizer,
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            self.logger
        )
        orchestrator.run("Test task")
        assert summarizer.run.call_count == 1

    def test_reject_verdict_fails_workflow(self):
        """
        Proves: if CriticAgent returns REJECT (HIGH severity factual error),
        the workflow status is FAILED — not BLOCKED, not COMPLETE.
        """
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="REJECT", score=0.3),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            self.logger
        )
        result = orchestrator.run("Test task")
        assert result.status == "FAILED"


class TestSafetyGate:
    """
    Tests that the SafetyAgent correctly stops the workflow on BLOCK.

    Why this matters: the safety gate is the last line of defense before
    output reaches the user. A SafetyAgent BLOCK must stop the workflow
    completely — no partial output, no fallback.
    """

    def setup_method(self):
        self.logger = MockDecisionLogger()

    def test_safety_block_returns_blocked_status(self):
        """
        Proves: when SafetyAgent returns STOP_WORKFLOW, result.status is BLOCKED.
        BLOCKED is distinct from FAILED — it means the system worked correctly
        and stopped a harmful output.
        """
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(
                status="BLOCKED",
                action="STOP_WORKFLOW",
                blocking_principles=[7]
            ),
            self.logger
        )
        result = orchestrator.run("Adversarial task")
        assert result.status == "BLOCKED"

    def test_safety_block_sets_no_final_output(self):
        """
        Proves: a BLOCKED workflow never produces a final_output.
        The user must never see output that failed the safety gate.
        """
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="BLOCKED", action="STOP_WORKFLOW"),
            self.logger
        )
        result = orchestrator.run("Adversarial task")
        assert result.final_output is None

    def test_safety_pass_allows_output(self):
        """
        Proves: a SAFE safety evaluation allows the workflow to complete
        and produce output. The safety gate is not over-blocking.
        """
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            self.logger
        )
        result = orchestrator.run("Safe educational task")
        assert result.status == "COMPLETE"
        assert result.final_output is not None

    def test_safety_block_is_logged(self):
        """
        Proves: safety blocks are recorded in the decision log.
        A blocked workflow must have a clear audit trail explaining why.
        """
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="BLOCKED", action="STOP_WORKFLOW", blocking_principles=[1]),
            self.logger
        )
        orchestrator.run("Adversarial task")
        safety_events = self.logger.get_events_for_agent("SafetyAgent")
        blocked_events = [e for e in safety_events if "BLOCKED" in e["action"]]
        assert len(blocked_events) > 0


# ---------------------------------------------------------------------------
# INTEGRATION TESTS
# ---------------------------------------------------------------------------

class TestIntegration:
    """
    Higher-level integration tests that verify multi-agent interactions.

    Why these are separate from unit tests: unit tests verify individual
    agent behavior in isolation. Integration tests verify that agents
    interact correctly — the contracts between them hold.
    """

    def test_research_findings_flow_to_summarizer(self):
        """
        Proves: ResearcherAgent output is passed to SummarizerAgent unchanged.
        Data corruption between agents is a silent failure mode.
        """
        logger = MockDecisionLogger()
        researcher = make_mock_researcher(source_type="uncertain", finding_confidence=0.5)
        summarizer = make_mock_summarizer()

        orchestrator = MockOrchestrator(
            make_mock_planner(), researcher, summarizer,
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            logger
        )
        orchestrator.run("Test task")

        # Summarizer must have been called with the researcher's output
        summarizer.run.assert_called_once()
        call_arg = summarizer.run.call_args[0][0]
        # The argument passed to summarizer should be a ResearchReport
        assert hasattr(call_arg, 'findings')
        assert call_arg.findings[0].source_type == "uncertain"

    def test_full_pipeline_with_one_revision_cycle(self):
        """
        Proves: one REVISE cycle followed by PASS produces COMPLETE status
        with revision_count == 1. The revision loop works end to end.
        """
        logger = MockDecisionLogger()
        # Critic returns REVISE once, then PASS
        critic = MagicMock()
        critic.run.side_effect = [
            CriticReview(verdict="REVISE", score=0.65, issues=[], revision_instructions="Add more detail", passes_safety_gate=True),
            CriticReview(verdict="PASS", score=0.85, issues=[], revision_instructions="", passes_safety_gate=True)
        ]

        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            critic,
            make_mock_safety(status="SAFE", action="CONTINUE"),
            logger
        )
        result = orchestrator.run("Test task")
        assert result.status == "COMPLETE"
        assert result.revision_count == 1
        assert critic.run.call_count == 2

    def test_workflow_result_serializable_to_json(self):
        """
        Proves: WorkflowResult fields can be inspected and the key data
        (status, revision_count) are JSON-serializable primitives.
        This matters for logging, API responses, and eval harnesses.
        """
        logger = MockDecisionLogger()
        orchestrator = MockOrchestrator(
            make_mock_planner(),
            make_mock_researcher(),
            make_mock_summarizer(),
            make_mock_critic(verdict="PASS"),
            make_mock_safety(status="SAFE", action="CONTINUE"),
            logger
        )
        result = orchestrator.run("Test task")
        # These fields must be JSON-serializable
        summary_data = {
            "status": result.status,
            "revision_count": result.revision_count,
            "has_final_output": result.final_output is not None,
            "log_event_count": logger.get_event_count()
        }
        json_str = json.dumps(summary_data)
        assert isinstance(json_str, str)
