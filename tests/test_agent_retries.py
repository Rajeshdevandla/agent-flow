"""Focused tests for transient per-agent API retry behavior."""

from unittest.mock import MagicMock, patch

import pytest

from agents.base_agent import BaseAgent


class APIErrorWithStatus(Exception):
    def __init__(self, status_code):
        super().__init__(f"API returned {status_code}")
        self.status_code = status_code


def successful_response(text="Recovered"):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 4
    response.usage.output_tokens = 2
    return response


def test_retries_transient_failure_then_succeeds():
    client = MagicMock()
    client.messages.create.side_effect = [
        APIErrorWithStatus(429),
        successful_response(),
    ]
    agent = BaseAgent(client=client, max_retries=3)

    with patch("agents.base_agent.time.sleep") as sleep:
        result = agent.call_claude("hello")

    assert result == "Recovered"
    assert client.messages.create.call_count == 2
    sleep.assert_called_once_with(1)
    assert [call["success"] for call in agent.call_history] == [False, True]
    assert agent.call_history[0]["error_type"] == "APIErrorWithStatus"
    assert agent.call_history[1]["attempt"] == 2


@pytest.mark.parametrize("status_code", [408, 409, 429, 500, 503])
def test_retries_retryable_http_statuses(status_code):
    client = MagicMock()
    client.messages.create.side_effect = APIErrorWithStatus(status_code)
    agent = BaseAgent(client=client, max_retries=2)

    with patch("agents.base_agent.time.sleep") as sleep:
        with pytest.raises(APIErrorWithStatus):
            agent.call_claude("hello")

    assert client.messages.create.call_count == 2
    sleep.assert_called_once_with(1)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_permanent_http_errors_fail_immediately(status_code):
    client = MagicMock()
    client.messages.create.side_effect = APIErrorWithStatus(status_code)
    agent = BaseAgent(client=client, max_retries=3)

    with patch("agents.base_agent.time.sleep") as sleep:
        with pytest.raises(APIErrorWithStatus):
            agent.call_claude("hello")

    client.messages.create.assert_called_once()
    sleep.assert_not_called()
    assert len(agent.call_history) == 1
    assert agent.call_history[0]["success"] is False


def test_unknown_programming_error_is_not_retried():
    client = MagicMock()
    client.messages.create.side_effect = ValueError("invalid local state")
    agent = BaseAgent(client=client, max_retries=3)

    with patch("agents.base_agent.time.sleep") as sleep:
        with pytest.raises(ValueError):
            agent.call_claude("hello")

    client.messages.create.assert_called_once()
    sleep.assert_not_called()


def test_rejects_zero_retry_attempts():
    with pytest.raises(ValueError, match="at least 1"):
        BaseAgent(client=MagicMock(), max_retries=0)
