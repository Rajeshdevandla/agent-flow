"""Structured, persistent audit logging for AgentFlow workflows."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from uuid import uuid4


class DecisionLogger:
    """Collect workflow decisions and persist them as newline-delimited JSON."""

    def __init__(
        self,
        workflow_id: Optional[str] = None,
        log_dir: Optional[os.PathLike[str] | str] = None,
        persist: bool = True,
    ) -> None:
        self.workflow_id = workflow_id or f"wf_{uuid4().hex[:12]}"
        self.events: list[dict[str, Any]] = []
        self._lock = Lock()
        self._log = logging.getLogger(self.__class__.__name__)
        self._log_path: Optional[Path] = None

        if persist:
            directory = Path(log_dir or os.getenv("AGENTFLOW_LOG_DIR", "logs"))
            directory.mkdir(parents=True, exist_ok=True)
            safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", self.workflow_id)
            self._log_path = directory / f"{safe_id}.jsonl"

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Return a JSON-compatible value without breaking workflow execution."""
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return str(value)

    def _record(self, event_type: str, agent: str, payload: dict[str, Any]) -> dict:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_id": self.workflow_id,
            "event_type": event_type,
            "agent": agent,
            **{key: self._json_safe(value) for key, value in payload.items()},
        }

        with self._lock:
            self.events.append(event)
            if self._log_path is not None:
                try:
                    with self._log_path.open("a", encoding="utf-8") as log_file:
                        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                except OSError as error:
                    self._log.warning("Unable to persist decision log: %s", error)
        return event

    def log(self, agent: str, action_or_output: Any, data: Any = None) -> dict:
        """Log either ``(agent, output)`` or ``(agent, action, data)``."""
        if data is None:
            action = "AGENT_OUTPUT"
            output = action_or_output
        else:
            action = str(action_or_output)
            output = data
        return self._record("decision", agent, {"action": action, "output": output})

    def log_decision(
        self,
        *,
        agent: str,
        input: Any,
        output: Any,
        reasoning: str,
        confidence: float,
        time_taken: float,
    ) -> dict:
        """Log the structured decision format emitted by AgentFlow agents."""
        return self._record(
            "decision",
            agent,
            {
                "input": input,
                "output": output,
                "reasoning": reasoning,
                "confidence": confidence,
                "time_taken": time_taken,
            },
        )

    def log_api_call(self, record: dict[str, Any]) -> dict:
        """Log API telemetry emitted by :class:`BaseAgent`."""
        agent = str(record.get("agent", "UnknownAgent"))
        payload = {key: value for key, value in record.items() if key != "agent"}
        return self._record("api_call", agent, payload)

    def query(
        self,
        *,
        agent: Optional[str] = None,
        event_type: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """Return audit events matching the supplied filters."""
        return [
            event.copy()
            for event in self.events
            if (agent is None or event["agent"] == agent)
            and (event_type is None or event["event_type"] == event_type)
            and (success is None or event.get("success") is success)
        ]

    def generate_session_report(self) -> dict[str, Any]:
        """Return a serializable snapshot suitable for workflow responses."""
        agents = sorted({event["agent"] for event in self.events})
        api_calls = self.query(event_type="api_call")
        return {
            "workflow_id": self.workflow_id,
            "event_count": len(self.events),
            "agents": agents,
            "api_calls": len(api_calls),
            "successful_api_calls": sum(
                1 for event in api_calls if event.get("success") is True
            ),
            "events": [event.copy() for event in self.events],
        }

