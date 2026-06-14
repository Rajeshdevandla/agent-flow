# orchestrator/failure_recovery.py
"""
Failure Recovery - NEW
Handles agent failures gracefully so the system never completely breaks.

Provides fallback strategies for each agent type.
"""

import logging
from datetime import datetime


class FailureRecovery:
    """
    NEW - Handles agent failures gracefully.

    Ensures AgentFlow NEVER completely fails - always returns something
    useful to the user even when individual agents fail.

    Recovery Strategies:
    - planner: Return hardcoded 2-step plan
    - researcher: Return empty findings with warning
    - summarizer: Return raw research text
    - critic: Skip critique and pass through
    - safety: Default to WARN_USER (err on side of caution)
    - evaluator: Return zero scores
    """

    def __init__(self):
        self._log = logging.getLogger("FailureRecovery")
        self.recovery_count = 0
        self.recovery_log = []

    def recover(self, agent_name: str, error: str, context: str = "") -> dict:
        """
        Main recovery method. Returns a safe fallback for any agent failure.
        """
        self.recovery_count += 1

        recovery_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "error": error[:200],
            "context": context[:100] if context else "",
            "recovery_number": self.recovery_count
        }
        self.recovery_log.append(recovery_entry)

        self._log.warning(f"Recovery #{self.recovery_count} for {agent_name}: {error[:100]}")

        # Route to appropriate recovery strategy
        recovery_strategies = {
            "planner": self._recover_planner,
            "researcher": self._recover_researcher,
            "summarizer": self._recover_summarizer,
            "critic": self._recover_critic,
            "safety": self._recover_safety,
            "evaluator": self._recover_evaluator
        }

        strategy = recovery_strategies.get(agent_name, self._recover_generic)
        return strategy(error, context)

    def _recover_planner(self, error: str, context: str) -> dict:
        """Fallback plan when PlannerAgent fails."""
        return {
            "task": context,
            "steps": [
                {
                    "step_number": 1,
                    "action": f"Research information about: {context}",
                    "agent": "ResearcherAgent",
                    "depends_on": [],
                    "risk": "May have incomplete information",
                    "estimated_time_seconds": 15
                },
                {
                    "step_number": 2,
                    "action": "Summarize findings into clear response",
                    "agent": "SummarizerAgent",
                    "depends_on": [1],
                    "risk": None,
                    "estimated_time_seconds": 10
                }
            ],
            "confidence": 30,
            "estimated_total_time_seconds": 25,
            "complexity": "LOW",
            "reasoning": f"Emergency fallback - PlannerAgent failed: {error[:100]}",
            "is_fallback": True,
            "is_recovery": True
        }

    def _recover_researcher(self, error: str, context: str) -> dict:
        """Fallback when ResearcherAgent fails."""
        return {
            "findings": [],
            "summary": f"Unable to complete research due to error: {error[:100]}",
            "data_quality": "INSUFFICIENT",
            "key_uncertainties": ["Research agent failed - no data collected"],
            "recommendation": "Retry the request or contact support",
            "is_recovery": True
        }

    def _recover_summarizer(self, error: str, context: str) -> dict:
        """Fallback when SummarizerAgent fails - return raw data."""
        return {
            "summary": f"Summary generation failed. Raw information: {context[:300]}",
            "reading_level": "technical",
            "word_count": len(context.split()),
            "key_points": [],
            "contradictions_found": [],
            "key_uncertainty": "Summarization failed - this is raw data",
            "confidence": "LOW",
            "sources_used": [],
            "is_recovery": True
        }

    def _recover_critic(self, error: str, context: str) -> dict:
        """Fallback when CriticAgent fails - pass through with warning."""
        return {
            "verdict": "PASS",
            "scores": {"accuracy": 50, "completeness": 50, "consistency": 50,
                       "clarity": 50, "safety": 100},
            "overall_score": 60,
            "issues": [{"category": "ACCURACY", "description": "Critic failed - unchecked",
                        "severity": "LOW", "suggestion": "Manual review recommended"}],
            "strengths": [],
            "revision_needed": False,
            "revision_instructions": "",
            "confidence": 0,
            "is_recovery": True,
            "warning": "Critic agent failed - response passed without full review"
        }

    def _recover_safety(self, error: str, context: str) -> dict:
        """
        Fallback when SafetyAgent fails.
        Err on the side of caution - warn the user.
        """
        return {
            "safe": False,
            "violations": ["Safety check failed due to error"],
            "severity": "MEDIUM",
            "action": "WARN_USER",
            "reason": f"Safety check failed: {error[:100]}. Manual review recommended.",
            "violated_principles": [],
            "is_recovery": True
        }

    def _recover_evaluator(self, error: str, context: str) -> dict:
        """Fallback when EvaluatorAgent fails."""
        return {
            "total_score": 50,
            "grade": "C",
            "quality": {"scores": {}, "total_score": 50},
            "efficiency": {"overall_efficiency": 50},
            "recommendations": ["Evaluation failed - manual review needed"],
            "error": error[:100],
            "is_recovery": True
        }

    def _recover_generic(self, error: str, context: str) -> dict:
        """Generic fallback for unknown agents."""
        return {
            "status": "AGENT_FAILURE",
            "error": error[:200],
            "is_recovery": True,
            "message": "Agent failed and recovery was applied"
        }

    def get_recovery_stats(self) -> dict:
        """Returns statistics about recoveries in this session."""
        return {
            "total_recoveries": self.recovery_count,
            "recoveries": self.recovery_log,
            "agents_that_failed": list(set(r["agent"] for r in self.recovery_log))
        }
