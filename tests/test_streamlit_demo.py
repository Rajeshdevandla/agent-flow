"""User-flow checks against the shipped Streamlit entrypoint."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
CASES = (
    (
        "LLM risks in medical diagnosis",
        "Non-technical",
        "Large language models can help clinicians",
        "92",
    ),
    (
        "RAG assistant for company documents",
        "Technical",
        "Use an ingestion pipeline",
        "94",
    ),
    (
        "AI customer-support assistant",
        "Business and technical",
        "Start with an agent-assist workflow",
        "93",
    ),
)
AGENTS = (
    "PlannerAgent",
    "ResearcherAgent",
    "SummarizerAgent",
    "CriticAgent",
    "SafetyAgent",
    "EvaluatorAgent",
)


def new_demo(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppTest.from_file(str(APP), default_timeout=10).run()


def assert_waiting(app):
    assert not app.exception
    cards = [
        item.value for item in app.markdown if '<div class="agent-card">' in item.value
    ]
    assert len(cards) == 6
    assert all("— waiting" in card for card in cards)
    assert not app.metric
    assert "Final response" not in [item.value for item in app.subheader]


def assert_completed(app, prefix, score):
    assert not app.exception
    cards = [
        item.value for item in app.markdown if '<div class="agent-card">' in item.value
    ]
    assert len(cards) == 6
    for agent, card in zip(AGENTS, cards):
        assert f"<strong>{agent}</strong> — complete" in card
    assert [item.value for item in app.subheader].count("Final response") == 1
    assert len([item for item in app.markdown if item.value.startswith(prefix)]) == 1
    assert {item.label: item.value for item in app.metric} == {
        "Agents completed": "6 / 6",
        "Safety status": "PASS",
        "Evaluation": score,
    }


@pytest.mark.parametrize("name,audience,prefix,score", CASES)
def test_scenario_results_survive_reruns(monkeypatch, name, audience, prefix, score):
    app = new_demo(monkeypatch)
    assert app.selectbox[0].options == [case[0] for case in CASES]
    assert any("curated, deterministic examples" in item.value for item in app.markdown)
    app.selectbox[0].select(name).run()
    assert_waiting(app)
    assert app.text_input[0].value == audience
    app.button[0].click().run()
    assert_completed(app, prefix, score)
    app.run()
    assert_completed(app, prefix, score)
    app.button[0].click().run()
    assert_completed(app, prefix, score)


def test_switching_scenarios_clears_previous_results(monkeypatch):
    app = new_demo(monkeypatch)
    for name, _, prefix, score in (*CASES, CASES[0]):
        app.selectbox[0].select(name).run()
        assert_waiting(app)
        app.button[0].click().run()
        assert_completed(app, prefix, score)


def test_completed_results_do_not_leak_to_another_session(monkeypatch):
    first = new_demo(monkeypatch)
    first.button[0].click().run()
    assert_completed(first, CASES[0][2], CASES[0][3])
    assert_waiting(new_demo(monkeypatch))
