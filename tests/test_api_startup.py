"""Exercise the shipped API, not the test-only mock orchestrator."""

import json
from itertools import product
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

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


def workflow_model_client(repeats=1):
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
        for output in responses * repeats
    ]
    return model_client


@pytest.mark.parametrize("task", ["", "   ", "\t\n\r", "\u00a0\u2003"])
def test_blank_workflow_task_is_rejected_before_client_creation(monkeypatch, task):
    model_client = workflow_model_client()
    get_client = MagicMock(return_value=model_client)
    monkeypatch.setattr(main, "get_client", get_client)
    with TestClient(main.app) as client:
        response = client.post("/workflow/run", json={"task": task})

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "task"]
    get_client.assert_not_called()
    model_client.messages.create.assert_not_called()


@pytest.mark.parametrize(
    "task", ["Explain retrieval", "  Explain retrieval\n  in 日本語\n"]
)
def test_real_workflow_route_runs_all_agents_without_network(monkeypatch, task):
    model_client = workflow_model_client()
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    with TestClient(main.app) as client:
        response = client.post("/workflow/run", json={"task": task})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["task"] == task
    assert (
        task
        in model_client.messages.create.call_args_list[0].kwargs["messages"][0][
            "content"
        ]
    )
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


def test_workflow_ids_and_audit_records_are_distinct_with_frozen_clock(monkeypatch):
    model_client = workflow_model_client(repeats=2)
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    monkeypatch.setattr(
        main,
        "time",
        SimpleNamespace(time=lambda: 1792848000.0, perf_counter=lambda: 0.0),
    )
    loggers = []
    original_logger = main.DecisionLogger

    class CapturedLogger(original_logger):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            loggers.append(self)

    monkeypatch.setattr(main, "DecisionLogger", CapturedLogger)
    with TestClient(main.app) as client:
        responses = [
            client.post("/workflow/run", json={"task": task})
            for task in ("Explain retrieval", "Explain embeddings")
        ]

    assert all(response.status_code == 200 for response in responses)
    results = [response.json() for response in responses]
    assert results[0]["workflow_id"] != results[1]["workflow_id"]
    assert len(loggers) == 2
    for result, logger in zip(results, loggers):
        assert result["workflow_id"].startswith("wf_")
        report = logger.generate_session_report()
        assert report["workflow_id"] == result["workflow_id"]
        assert report["event_count"] == 6
        assert all(e["workflow_id"] == result["workflow_id"] for e in report["events"])
        assert result["final_response"] == "A grounded summary."
    assert model_client.messages.create.call_count == 12


@pytest.mark.parametrize(
    "options,retry",
    [(options, False) for options in product((False, True), repeat=3)]
    + [((True, True, True), True)],
)
def test_api_reports_usage_for_executed_agents(monkeypatch, options, retry):
    model_client = workflow_model_client()
    responses = list(model_client.messages.create.side_effect)
    names = [
        "PlannerAgent",
        "ResearcherAgent",
        "SummarizerAgent",
        "CriticAgent",
        "SafetyAgent",
        "EvaluatorAgent",
    ]
    enabled = (True, True, True) + options
    expected = {}
    selected = []
    for index, (name, response, active) in enumerate(zip(names, responses, enabled), 1):
        if active:
            response.usage = SimpleNamespace(
                input_tokens=10 * index, output_tokens=index
            )
            expected[name] = 11 * index
            selected.append(response)
    model_client.messages.create.side_effect = (
        [TimeoutError("Temporary failure")] if retry else []
    ) + selected * 2
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    monkeypatch.setattr("agents.base_agent.time.sleep", lambda seconds: None)
    request = dict(zip(("enable_critic", "enable_safety", "enable_evaluator"), options))
    with TestClient(main.app) as client:
        for _ in range(2):
            response = client.post(
                "/workflow/run", json={"task": "Explain retrieval", **request}
            )
            assert response.status_code == 200, response.text
            result = response.json()
            actual = {
                agent["agent_name"]: agent["tokens_used"]
                for agent in result["agent_results"]
            }
            assert actual == expected
            assert result["total_tokens"] == sum(expected.values())
    assert model_client.messages.create.call_count == len(selected) * 2 + int(retry)


@pytest.mark.parametrize(
    "options,retry",
    [
        ((True, True, True), False),
        ((False, False, False), False),
        ((True, False, True), False),
        ((True, True, True), True),
    ],
)
def test_api_measures_agent_durations_with_monotonic_clock(monkeypatch, options, retry):
    model_client = workflow_model_client()
    responses = list(model_client.messages.create.side_effect)
    names = [
        "PlannerAgent",
        "ResearcherAgent",
        "SummarizerAgent",
        "CriticAgent",
        "SafetyAgent",
        "EvaluatorAgent",
    ]
    enabled = (True, True, True) + options
    selected = [
        (name, response, index / 4)
        for index, (name, response, active) in enumerate(
            zip(names, responses, enabled), 1
        )
        if active
    ]
    clock = SimpleNamespace(elapsed=0.0)

    def advance(seconds):
        clock.elapsed += seconds

    calls = iter(([None] if retry else []) + selected * 2)

    def respond(**kwargs):
        item = next(calls)
        if item is None:
            advance(0.5)
            raise TimeoutError("Temporary failure")
        _, response, duration = item
        advance(duration)
        return response

    model_client.messages.create.side_effect = respond
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    monkeypatch.setattr(
        main,
        "time",
        SimpleNamespace(
            perf_counter=lambda: clock.elapsed,
            time=lambda: 2000 - clock.elapsed,
        ),
    )
    monkeypatch.setattr("agents.base_agent.time.sleep", advance)
    request = dict(zip(("enable_critic", "enable_safety", "enable_evaluator"), options))
    with TestClient(main.app) as client:
        for request_index in range(2):
            response = client.post(
                "/workflow/run", json={"task": "Explain retrieval", **request}
            )
            assert response.status_code == 200, response.text
            result = response.json()
            expected = {name: duration for name, _, duration in selected}
            if retry and request_index == 0:
                expected["PlannerAgent"] += 1.5  # Failed call plus retry backoff.
            actual = {
                agent["agent_name"]: agent["duration"]
                for agent in result["agent_results"]
            }
            assert actual == pytest.approx(expected)
            assert result["total_duration"] == pytest.approx(sum(expected.values()))
            assert result["final_response"] == "A grounded summary."
    assert model_client.messages.create.call_count == len(selected) * 2 + int(retry)


@pytest.mark.parametrize("stage", range(6))
def test_api_hides_unexpected_model_errors(monkeypatch, caplog, stage):
    model_client = workflow_model_client()
    responses = list(model_client.messages.create.side_effect)
    private_detail = "PRIVATE_PROVIDER_DETAIL token=example-secret /internal/config"
    model_client.messages.create.side_effect = responses[:stage] + [
        ValueError(private_detail)
    ]
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    with TestClient(main.app) as client:
        response = client.post("/workflow/run", json={"task": "Explain retrieval"})
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Unable to complete the workflow. Please try again later."
    }
    assert private_detail not in response.text
    assert private_detail not in caplog.text
    assert "ValueError" in caplog.text
    assert model_client.messages.create.call_count == stage + 1


def test_api_preserves_safety_block_response(monkeypatch):
    model_client = workflow_model_client()
    responses = list(model_client.messages.create.side_effect)
    responses[4].content[0].text = json.dumps(
        {"action": "BLOCK", "issues": ["Unsafe content"], "score": 0, "violations": []}
    )
    model_client.messages.create.side_effect = responses
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    with TestClient(main.app) as client:
        response = client.post("/workflow/run", json={"task": "Explain retrieval"})
    assert response.status_code == 400
    assert "Response blocked by SafetyAgent" in response.json()["detail"]
    assert model_client.messages.create.call_count == 5
