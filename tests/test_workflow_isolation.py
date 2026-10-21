"""Sequential runs on one engine must keep independent audit and usage data."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orchestrator.workflow_engine import WorkflowEngine


def responses(summary, action="PASS", tokens=10):
    outputs = [
        {"steps": [], "confidence": 90},
        {"findings": [], "data_quality": "HIGH"},
        {"summary": summary, "confidence": "HIGH", "word_count": 3},
        {"verdict": "PASS", "overall_score": 90, "issues": []},
        {"action": action, "issues": [], "score": 95, "violations": []},
        {"scores": {"accuracy": 90}, "total_score": 90},
    ]
    return [
        SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(o))],
            usage=SimpleNamespace(input_tokens=tokens, output_tokens=tokens),
        )
        for o in outputs
    ]


@pytest.mark.parametrize("first_outcome", ["success", "block", "recovery", "failure"])
def test_reused_engine_isolates_runs(monkeypatch, first_outcome):
    first_responses = responses("FIRST_PRIVATE_RESPONSE")
    if first_outcome == "block":
        first_responses = responses("FIRST_PRIVATE_RESPONSE", action="BLOCK")[:5]
    elif first_outcome == "recovery":
        first_responses = first_responses[:4] + [RuntimeError("Safety unavailable")]
    elif first_outcome == "failure":
        first_responses = first_responses[:3]
    client = MagicMock()
    client.messages.create.side_effect = first_responses + responses(
        "SECOND_RESPONSE", tokens=20
    )
    monkeypatch.setattr("agents.base_agent.anthropic.Anthropic", lambda: client)
    engine = WorkflowEngine()
    agents = [
        engine.planner,
        engine.researcher,
        engine.summarizer,
        engine.critic,
        engine.safety,
        engine.evaluator,
    ]
    original_critic_loop = engine._run_critic_loop
    if first_outcome == "failure":

        def fail(*args):
            raise RuntimeError("Unexpected orchestration failure")

        monkeypatch.setattr(engine, "_run_critic_loop", fail)
    first = engine.run("FIRST_PRIVATE_TASK")
    assert (
        first["status"]
        == {
            "success": "SUCCESS",
            "block": "BLOCKED",
            "recovery": "BLOCKED",
            "failure": "PIPELINE_FAILURE",
        }[first_outcome]
    )
    first_snapshot = deepcopy(first)
    first_logger = engine.logger
    first_report = first_logger.generate_session_report()
    first_recovery = engine.recovery
    assert first_recovery.recovery_count == (1 if first_outcome == "recovery" else 0)
    monkeypatch.setattr(engine, "_run_critic_loop", original_critic_loop)

    second = engine.run("SECOND_TASK")

    assert second["status"] == "SUCCESS"
    assert second["response"] == "SECOND_RESPONSE"
    log = second["decision_log"]
    assert log["workflow_id"] != first["decision_log"]["workflow_id"]
    assert log["api_call_count"] == 6
    assert log["total_tokens"] == 240
    assert second["evaluation"]["tokens_used"] == 200  # Before evaluation's own call.
    assert "FIRST_PRIVATE" not in json.dumps(second)
    assert all(event["workflow_id"] == log["workflow_id"] for event in log["events"])
    assert engine.recovery.get_recovery_stats()["total_recoveries"] == 0
    assert first == first_snapshot
    assert first_logger.generate_session_report() == first_report
    assert first_recovery.recovery_count == (1 if first_outcome == "recovery" else 0)
    for agent in agents:
        assert agent.client is client
        assert agent.logger is engine.logger
        assert len(agent.call_history) == 1
        assert agent.total_tokens_used == 40
