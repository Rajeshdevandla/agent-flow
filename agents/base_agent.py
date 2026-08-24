"""Shared Anthropic client, retry, parsing, and telemetry support for agents."""

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

import anthropic


class BaseAgent:
    """Base class used by every AgentFlow agent."""

    MODEL = "claude-opus-4-5"
    MAX_TOKENS = 4096
    MAX_RETRIES = 3
    RETRYABLE_STATUS_CODES = {408, 409, 429}
    RETRYABLE_ERROR_NAMES = {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
    }

    def __init__(
        self,
        client: Optional[Any] = None,
        model: Optional[str] = None,
        max_retries: int = MAX_RETRIES,
        logger: Optional[Any] = None,
        config: Optional[dict] = None,
    ):
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")

        self.client = client or anthropic.Anthropic()
        self.model = model or self.MODEL
        self.max_retries = max_retries
        self.logger = logger
        self.config = config or {}
        self.call_history = []
        self.total_tokens_used = 0
        self._log = logging.getLogger(self.__class__.__name__)

    @classmethod
    def _is_retryable_error(cls, error: Exception) -> bool:
        """Return whether an API failure is likely to succeed when retried."""
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True

        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return (
                status_code in cls.RETRYABLE_STATUS_CODES
                or 500 <= status_code < 600
            )

        # Keep this compatible with supported Anthropic SDK versions without
        # requiring tests to construct SDK exceptions with HTTP request objects.
        return error.__class__.__name__ in cls.RETRYABLE_ERROR_NAMES

    def _record_call(
        self,
        *,
        started: float,
        attempt: int,
        success: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: Optional[Exception] = None,
    ) -> None:
        record = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.__class__.__name__,
            "attempt": attempt,
            "time_ms": round((time.time() - started) * 1000, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "success": success,
        }
        if error is not None:
            record["error_type"] = error.__class__.__name__

        self.call_history.append(record)
        if self.logger:
            self.logger.log_api_call(record)

    def call_claude(
        self,
        prompt: Optional[str] = None,
        system: str = "",
        *,
        user: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call Claude, retrying only failures that are safe to retry."""
        user_message = user if user is not None else (prompt or "")
        token_limit = max_tokens or self.MAX_TOKENS
        started = time.time()

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=token_limit,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                )
                content = response.content[0].text
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0)
                if not isinstance(input_tokens, int):
                    input_tokens = 0
                if not isinstance(output_tokens, int):
                    output_tokens = 0
                self.total_tokens_used += input_tokens + output_tokens

                self._record_call(
                    started=started,
                    attempt=attempt,
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                return content
            except Exception as error:
                self._record_call(
                    started=started,
                    attempt=attempt,
                    success=False,
                    error=error,
                )
                retryable = self._is_retryable_error(error)
                if not retryable or attempt >= self.max_retries:
                    raise

                wait_seconds = 2 ** (attempt - 1)
                self._log.warning(
                    "Transient agent call failure (%s); retrying in %ss "
                    "(attempt %s/%s)",
                    error.__class__.__name__,
                    wait_seconds,
                    attempt,
                    self.max_retries,
                )
                time.sleep(wait_seconds)

        raise RuntimeError("Agent call failed without an exception")

    def parse_json(self, response: str) -> Any:
        """Parse JSON, including JSON wrapped in a Markdown code fence."""
        cleaned = response.strip()
        if cleaned.startswith("~~~"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()
        elif cleaned.startswith(chr(96) * 3):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        self._log.error("Failed to parse JSON response")
        return {"error": "JSON_PARSE_FAILED", "raw": response}

    def handle_failure(self, error: str) -> str:
        return json.dumps(
            {
                "status": "AGENT_FAILURE",
                "agent": self.__class__.__name__,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_stats(self) -> dict:
        calls = len(self.call_history)
        return {
            "agent": self.__class__.__name__,
            "total_calls": calls,
            "total_tokens": self.total_tokens_used,
            "avg_time_ms": (
                sum(call["time_ms"] for call in self.call_history) / calls if calls else 0
            ),
            "success_rate": (
                sum(1 for call in self.call_history if call["success"]) / calls
                if calls
                else 0
            ),
        }
