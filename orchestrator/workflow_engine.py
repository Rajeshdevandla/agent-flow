# orchestrator/workflow_engine.py
"""
Workflow Engine - Upgraded
Orchestrates the 6-agent pipeline with full logging and recovery.

UPGRADES FROM ORIGINAL:
- Now coordinates all 6 agents (added Critic, Safety, Evaluator)
- Full decision logging at every step
- Automatic retry on agent failure
- Safety gate before returning to user
- Performance metrics collection
"""

import time
from agents.planner_agent import PlannerAgent
from agents.researcher_agent import ResearcherAgent
from agents.summarizer_agent import SummarizerAgent
from agents.critic_agent import CriticAgent
from agents.safety_agent import SafetyAgent
from agents.evaluator_agent import EvaluatorAgent
from orchestrator.decision_logger import DecisionLogger
from orchestrator.failure_recovery import FailureRecovery


class WorkflowEngine:
    """
    Upgraded orchestrator that coordinates all 6 agents.

    FLOW:
    User Task
    -> PlannerAgent (plan with confidence)
    -> ResearcherAgent (gather info with citations)
    -> SummarizerAgent (synthesize for audience)
    -> CriticAgent (quality review - loop if needed)
    -> SafetyAgent (safety gate - block if needed)
    -> EvaluatorAgent (score the workflow)
    -> Final Response + Decision Log + Quality Score + Safety Report
    """

    MAX_REVISION_LOOPS = 2  # Max times Critic can send back for revision

    def __init__(self, user_type: str = "non-technical"):
        self.logger = DecisionLogger()
        self.recovery = FailureRecovery()
        self.user_type = user_type

        # Initialize all 6 agents with shared logger
        self.planner = PlannerAgent(logger=self.logger)
        self.researcher = ResearcherAgent(logger=self.logger)
        self.summarizer = SummarizerAgent(logger=self.logger)
        self.critic = CriticAgent(logger=self.logger)
        self.safety = SafetyAgent(logger=self.logger)
        self.evaluator = EvaluatorAgent(logger=self.logger)

        self.agent_outputs = []
        self.start_time = None

    def run(self, user_task: str) -> dict:
        """
        Main entry point. Runs the complete 6-agent pipeline.
        Returns final response with full audit trail.
        """
        self.start_time = time.time()
        self.agent_outputs = []

        print(f"Starting AgentFlow pipeline for: {user_task[:100]}")

        try:
            # Step 1: Plan
            print("Step 1/6: PlannerAgent...")
            plan = self._run_with_recovery("planner", self.planner.plan, user_task)
            self.agent_outputs.append({"agent": "PlannerAgent", "output": plan})

            # Step 2: Research
            print("Step 2/6: ResearcherAgent...")
            research_context = str(plan.get("steps", []))
            research = self._run_with_recovery(
                "researcher",
                self.researcher.research,
                user_task,
                research_context
            )
            self.agent_outputs.append({"agent": "ResearcherAgent", "output": research})

            # Step 3: Summarize
            print("Step 3/6: SummarizerAgent...")
            summary = self._run_with_recovery(
                "summarizer",
                self.summarizer.summarize,
                research,
                self.user_type
            )
            self.agent_outputs.append({"agent": "SummarizerAgent", "output": summary})

            # Step 4: Critic Review Loop
            print("Step 4/6: CriticAgent...")
            final_summary = self._run_critic_loop(
                summary.get("summary", str(summary)),
                user_task
            )

            # Step 5: Safety Check
            print("Step 5/6: SafetyAgent...")
            safety_result = self._run_with_recovery(
                "safety",
                self.safety.check,
                final_summary
            )
            self.agent_outputs.append({"agent": "SafetyAgent", "output": safety_result})

            # Handle safety block
            if safety_result.get("action") == "BLOCK":
                return self._handle_blocked_response(safety_result, user_task)

            # Step 6: Evaluate
            print("Step 6/6: EvaluatorAgent...")
            time_taken = (time.time() - self.start_time) * 1000
            total_tokens = sum(
                a.total_tokens_used for a in [
                    self.planner, self.researcher, self.summarizer,
                    self.critic, self.safety, self.evaluator
                ]
            )

            evaluation = self._run_with_recovery(
                "evaluator",
                self.evaluator.evaluate_workflow,
                user_task,
                self.agent_outputs,
                final_summary,
                time_taken,
                total_tokens
            )
            self.agent_outputs.append({"agent": "EvaluatorAgent", "output": evaluation})

            print(f"Pipeline complete! Score: {evaluation.get('total_score')}/100")

            return {
                "status": "SUCCESS",
                "response": final_summary,
                "safety": safety_result,
                "evaluation": evaluation,
                "decision_log": self.logger.generate_session_report(),
                "plan": plan,
                "warnings": self.safety.get_user_message(safety_result) if hasattr(self.safety, 'get_user_message') else ""
            }

        except Exception as e:
            return self._handle_pipeline_failure(str(e), user_task)

    def _run_with_recovery(self, agent_name: str, func, *args) -> any:
        """
        Runs an agent function with automatic failure recovery.
        """
        try:
            return func(*args)
        except Exception as e:
            self.logger._log.error(f"{agent_name} failed: {e}")
            return self.recovery.recover(agent_name, str(e), args[0] if args else "")

    def _run_critic_loop(self, response: str, task: str) -> str:
        """
        Runs the critic review loop with max revision attempts.
        Returns revised response or original if passes.
        """
        current_response = response
        revision_count = 0

        for attempt in range(self.MAX_REVISION_LOOPS + 1):
            critique = self._run_with_recovery(
                "critic",
                self.critic.critique,
                current_response,
                task
            )
            self.agent_outputs.append({
                "agent": "CriticAgent",
                "output": critique,
                "attempt": attempt + 1
            })

            if not self.critic.should_revise(critique):
                print(f"Critic: PASS on attempt {attempt + 1}")
                break

            if revision_count >= self.MAX_REVISION_LOOPS:
                print(f"Critic: Max revisions reached, using current response")
                break

            # Get revision instructions and re-summarize
            revision_instructions = self.critic.get_revision_instructions(critique)
            if revision_instructions:
                print(f"Critic: NEEDS_REVISION (attempt {attempt + 1}), revising...")
                revised = self._revise_response(current_response, revision_instructions)
                if revised:
                    current_response = revised
                    revision_count += 1

        return current_response

    def _revise_response(self, response: str, instructions: str) -> str:
        """
        Revises a response based on critic instructions.
        """
        from agents.base_agent import BaseAgent

        class QuickReviser(BaseAgent):
            pass

        reviser = QuickReviser(logger=self.logger)
        revision = reviser.call_claude(
            system="You are a revision editor. Fix the response based on instructions. Keep all accurate helpful content.",
            user=f"Original response:\n{response}\n\nRevision instructions:\n{instructions}\n\nRevised response:"
        )
        return revision

    def _handle_blocked_response(self, safety_result: dict, task: str) -> dict:
        """Returns appropriate response when safety blocks content."""
        return {
            "status": "BLOCKED",
            "response": "I cannot provide a response to this request as it raised safety concerns.",
            "safety": safety_result,
            "evaluation": {"total_score": 0, "grade": "F"},
            "decision_log": self.logger.generate_session_report(),
            "reason": safety_result.get("reason", "Safety check failed")
        }

    def _handle_pipeline_failure(self, error: str, task: str) -> dict:
        """Returns graceful failure response when pipeline breaks."""
        return {
            "status": "PIPELINE_FAILURE",
            "response": "I encountered an error while processing your request. Please try again.",
            "error": error,
            "decision_log": self.logger.generate_session_report(),
            "evaluation": {"total_score": 0, "grade": "F"}
        }
