"""Per-workflow decision and API-call audit records.

Records stay in memory. Callers can serialize a session report for persistence;
constructing a logger never writes user prompts or outputs to disk.
"""

from copy import deepcopy
from datetime import datetime, timezone
import logging
from uuid import uuid4


class DecisionLogger:
    """Implement the logging interface shared by the API and agent classes."""

    def __init__(self, workflow_id: str | None = None):
        self.workflow_id = workflow_id or f"wf_{uuid4().hex}"
        self._log = logging.getLogger(__name__)
        self._events: list[dict] = []

    def _record(self, event_type: str, data: dict) -> None:
        self._events.append(
            {
                **deepcopy(data),
                "event_type": event_type,
                "workflow_id": self.workflow_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def log(self, agent_name: str, output: dict) -> None:
        """Record a completed agent's structured output from the API route."""
        self._record("agent_output", {"agent": agent_name, "output": output})

    def log_decision(
        self,
        *,
        agent: str,
        input: str,
        output: str,
        reasoning: str,
        confidence: float,
        time_taken: float,
    ) -> None:
        """Record a decision using the keyword interface called by agents."""
        self._record(
            "decision",
            {
                "agent": agent,
                "input": input,
                "output": output,
                "reasoning": reasoning,
                "confidence": confidence,
                "time_taken": time_taken,
            },
        )

    def log_api_call(self, record: dict) -> None:
        """Retain attempt, token usage, timing and error metadata from BaseAgent."""
        self._record("api_call", record)

    def get_events_for_agent(self, agent_name: str) -> list[dict]:
        return deepcopy(
            [event for event in self._events if event.get("agent") == agent_name]
        )

    def generate_session_report(self) -> dict:
        """Return an isolated, JSON-serializable snapshot for the workflow."""
        api_calls = [e for e in self._events if e["event_type"] == "api_call"]
        return {
            "workflow_id": self.workflow_id,
            "event_count": len(self._events),
            "decision_count": sum(e["event_type"] == "decision" for e in self._events),
            "api_call_count": len(api_calls),
            "total_tokens": sum(
                e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in api_calls
            ),
            "events": deepcopy(self._events),
        }
