"""Malformed model reviews must never authorize unchecked content."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agents.safety_agent import SafetyAgent
from api import main
from orchestrator.workflow_engine import WorkflowEngine

INVALID_REVIEWS = [
    "not JSON",
    "null",
    "[]",
    "1",
    "{}",
    '{"action": "UNKNOWN"}',
    '{"action": null}',
    json.dumps({"action": "PASS", "issues": [], "violations": []}),
    json.dumps({"action": "PASS", "issues": "none", "score": 95, "violations": []}),
    json.dumps({"action": "PASS", "issues": [], "score": True, "violations": []}),
    json.dumps({"action": "PASS", "issues": [], "score": 101, "violations": []}),
    json.dumps(
        {"action": "PASS", "issues": [], "score": float("nan"), "violations": []}
    ),
    json.dumps({"action": "PASS", "issues": [], "score": 95, "violations": [1]}),
]


def model_response(text):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


@pytest.mark.parametrize("raw", INVALID_REVIEWS)
def test_invalid_review_blocks_without_echoing_model_output(raw):
    client = MagicMock()
    client.messages.create.return_value = model_response(raw)
    result = SafetyAgent(client=client).run("Unchecked candidate")
    assert result["action"] == "BLOCK"
    assert result["score"] == 0
    assert result["error"] == "INVALID_SAFETY_REVIEW"
    assert result["issues"] == ["Safety review was invalid; response withheld."]
    assert "raw" not in result


@pytest.mark.parametrize("surface", ["engine", "api"])
@pytest.mark.parametrize("raw", ["{}", "null", '{"action":"UNKNOWN"}'])
def test_invalid_review_withholds_candidate_across_entrypoints(
    monkeypatch, surface, raw
):
    candidate = "UNCHECKED CANDIDATE CONTENT"
    outputs = [
        {"steps": [], "confidence": 90},
        {"findings": [], "data_quality": "HIGH"},
        {"summary": candidate, "confidence": "HIGH", "word_count": 3},
        {"verdict": "PASS", "overall_score": 90, "issues": []},
    ]
    client = MagicMock()
    client.messages.create.side_effect = [
        model_response(json.dumps(o)) for o in outputs
    ] + [model_response(raw)]
    if surface == "engine":
        monkeypatch.setattr("agents.base_agent.anthropic.Anthropic", lambda: client)
        engine = WorkflowEngine()
        result = engine.run("Explain retrieval")
        assert result["status"] == "BLOCKED"
        assert candidate not in result["response"]
        assert result["safety"]["error"] == "INVALID_SAFETY_REVIEW"
        assert engine.evaluator.call_history == []
    else:
        monkeypatch.setattr(main, "get_client", lambda: client)
        with TestClient(main.app) as api:
            result = api.post("/workflow/run", json={"task": "Explain retrieval"})
        assert result.status_code == 400, result.text
        assert candidate not in result.text
    assert client.messages.create.call_count == 5


def test_engine_safety_exception_also_withholds_candidate(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("agents.base_agent.anthropic.Anthropic", lambda: client)
    engine = WorkflowEngine()
    monkeypatch.setattr(engine.planner, "plan", lambda task: {"steps": []})
    monkeypatch.setattr(engine.researcher, "research", lambda *args: {})
    monkeypatch.setattr(
        engine.summarizer, "summarize", lambda *args: {"summary": "UNCHECKED"}
    )
    monkeypatch.setattr(engine.critic, "critique", lambda *args: {"verdict": "PASS"})

    def fail(*args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(engine.safety, "run", fail)
    result = engine.run("Explain retrieval")
    assert result["status"] == "BLOCKED"
    assert "UNCHECKED" not in result["response"]
    assert result["safety"]["is_recovery"] is True
    assert engine.evaluator.call_history == []
