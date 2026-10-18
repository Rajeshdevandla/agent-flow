"""Test the production logger and its existing agent integration."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from agents.planner_agent import PlannerAgent
from orchestrator.decision_logger import DecisionLogger


def test_real_agent_records_decisions_and_api_usage():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps({"steps": [], "confidence": 80}))],
        usage=SimpleNamespace(input_tokens=12, output_tokens=8),
    )
    logger = DecisionLogger(workflow_id="wf-test")
    PlannerAgent(client=client, logger=logger).plan("Explain retrieval")

    report = logger.generate_session_report()
    assert report["workflow_id"] == "wf-test"
    assert report["event_count"] == 3
    assert report["decision_count"] == 2
    assert report["api_call_count"] == 1
    assert report["total_tokens"] == 20
    assert len(logger.get_events_for_agent("PlannerAgent")) == 3
    assert all(event["recorded_at"] for event in report["events"])
    assert json.loads(json.dumps(report)) == report


def test_logger_snapshots_do_not_mutate_or_leak_between_workflows():
    logger = DecisionLogger()
    other = DecisionLogger()
    output = {"findings": ["first"]}
    logger.log("ResearcherAgent", output)
    output["findings"].append("changed")

    report = logger.generate_session_report()
    report["events"][0]["output"]["findings"].append("report changed")
    events = logger.get_events_for_agent("ResearcherAgent")
    assert events[0]["output"] == {"findings": ["first"]}
    events.clear()
    assert logger.generate_session_report()["event_count"] == 1
    assert other.generate_session_report()["event_count"] == 0
    assert other.workflow_id != logger.workflow_id


def test_failed_api_attempt_preserves_error_metadata_and_zero_usage():
    logger = DecisionLogger()
    logger.log_api_call(
        {
            "agent": "SafetyAgent",
            "attempt": 1,
            "success": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "error_type": "TimeoutError",
        }
    )
    report = logger.generate_session_report()
    assert report["api_call_count"] == 1
    assert report["total_tokens"] == 0
    assert report["events"][0]["error_type"] == "TimeoutError"
    assert report["events"][0]["success"] is False
