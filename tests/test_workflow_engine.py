"""Run the production engine with only the external model client replaced."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orchestrator.workflow_engine import WorkflowEngine


@pytest.mark.parametrize(
    "action,issues,expected_warning",
    [
        ("PASS", [], ""),
        ("BLOCK", ["Unsafe content"], None),
        ("WARN_USER", ["Verify these claims."], "Safety warning: Verify these claims."),
        (
            "WARN_USER",
            [" Verify these claims. ", "", "Consult a qualified professional."],
            "Safety warning: Verify these claims. Consult a qualified professional.",
        ),
        (
            "WARN_USER",
            [],
            "Safety warning: Review this response carefully before using it.",
        ),
        (
            "WARN_USER",
            [" ", "\t"],
            "Safety warning: Review this response carefully before using it.",
        ),
    ],
)
def test_engine_reaches_safety_and_respects_its_decision(
    monkeypatch, action, issues, expected_warning
):
    summary = "The candidate response."
    safety = {
        "action": action,
        "issues": issues,
        "score": 0 if action == "BLOCK" else 100,
        "violations": [],
    }
    outputs = [
        {"steps": [], "confidence": 90},
        {"findings": [], "data_quality": "HIGH"},
        {"summary": summary, "confidence": "HIGH", "word_count": 4},
        {"verdict": "PASS", "overall_score": 90, "issues": []},
        safety,
    ]
    if action != "BLOCK":
        outputs.append({"scores": {"accuracy": 90}, "total_score": 90})
    client = MagicMock()
    client.messages.create.side_effect = [
        SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(output))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        for output in outputs
    ]
    monkeypatch.setattr("agents.base_agent.anthropic.Anthropic", lambda: client)
    engine = WorkflowEngine()

    result = engine.run("Explain retrieval")

    assert result["status"] == ("BLOCKED" if action == "BLOCK" else "SUCCESS"), result
    assert result["safety"] == safety
    assert client.messages.create.call_args_list[4].kwargs["messages"] == [
        {"role": "user", "content": summary}
    ]
    assert client.messages.create.call_count == len(outputs)
    assert result["decision_log"]["api_call_count"] == len(outputs)
    assert engine.agent_outputs[4] == {"agent": "SafetyAgent", "output": safety}
    if action == "BLOCK":
        assert summary not in result["response"]
        assert result["evaluation"]["total_score"] == 0
        assert engine.evaluator.call_history == []
    else:
        assert result["response"] == summary
        assert result["warnings"] == expected_warning
        assert result["evaluation"]["quality"]["scores"]["accuracy"] == 90
        assert engine.agent_outputs[-1]["agent"] == "EvaluatorAgent"
