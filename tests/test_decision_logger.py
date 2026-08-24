"""Tests for the production decision audit logger."""

import json

from orchestrator.decision_logger import DecisionLogger


def test_supports_api_and_agent_log_formats(tmp_path):
    logger = DecisionLogger("workflow-1", log_dir=tmp_path)

    logger.log("PlannerAgent", {"steps": 2})
    logger.log("SafetyAgent", "SAFETY_SAFE", {"action": "CONTINUE"})

    assert [event["action"] for event in logger.events] == [
        "AGENT_OUTPUT",
        "SAFETY_SAFE",
    ]
    assert logger.query(agent="SafetyAgent")[0]["output"]["action"] == "CONTINUE"


def test_persists_jsonl_and_generates_report(tmp_path):
    logger = DecisionLogger("workflow/unsafe-id", log_dir=tmp_path)
    logger.log_decision(
        agent="PlannerAgent",
        input="Plan this",
        output="Two steps",
        reasoning="Small task",
        confidence=0.9,
        time_taken=12.5,
    )
    logger.log_api_call(
        {
            "agent": "PlannerAgent",
            "attempt": 1,
            "success": True,
            "input_tokens": 10,
            "output_tokens": 5,
        }
    )

    log_path = tmp_path / "workflow_unsafe-id.jsonl"
    persisted = [json.loads(line) for line in log_path.read_text().splitlines()]
    report = logger.generate_session_report()

    assert persisted == logger.events
    assert report["event_count"] == 2
    assert report["agents"] == ["PlannerAgent"]
    assert report["api_calls"] == 1
    assert report["successful_api_calls"] == 1


def test_non_serializable_values_do_not_break_logging(tmp_path):
    logger = DecisionLogger("workflow-2", log_dir=tmp_path)

    event = logger.log("EvaluatorAgent", {"value": object()})

    assert isinstance(event["output"], str)
    assert (tmp_path / "workflow-2.jsonl").exists()

