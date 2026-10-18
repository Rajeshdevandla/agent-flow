"""Exercise the shipped API, not the test-only mock orchestrator."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api import main


def test_api_starts_without_credentials_and_reports_degraded_health(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
        agents = client.get("/agents")
        assert agents.status_code == 200
        assert len(agents.json()["agents"]) == 6
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "degraded"
        assert health.json()["anthropic_connected"] is False


def test_real_workflow_route_runs_all_agents_without_network(monkeypatch):
    responses = [
        {"steps": [], "confidence": 90},
        {"findings": [], "data_quality": "HIGH"},
        {"summary": "A grounded summary.", "confidence": "HIGH", "word_count": 3},
        {"verdict": "PASS", "overall_score": 90, "issues": []},
        {"action": "PASS", "issues": [], "score": 95, "violations": []},
        {"scores": {"accuracy": 90}, "total_score": 90, "grade": "A"},
    ]
    model_client = MagicMock()
    model_client.messages.create.side_effect = [
        SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(output))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        for output in responses
    ]
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    with TestClient(main.app) as client:
        response = client.post("/workflow/run", json={"task": "Explain retrieval"})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["final_response"] == "A grounded summary."
    assert [agent["agent_name"] for agent in result["agent_results"]] == [
        "PlannerAgent",
        "ResearcherAgent",
        "SummarizerAgent",
        "CriticAgent",
        "SafetyAgent",
        "EvaluatorAgent",
    ]
    assert result["safety_report"]["action"] == "PASS"
    assert result["quality_scores"]["total_score"] == 90
    assert model_client.messages.create.call_count == 6
