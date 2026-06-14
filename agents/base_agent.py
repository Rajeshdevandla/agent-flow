# agents/base_agent.py
"""
Base Agent — Upgraded
Foundation class for all AgentFlow agents.
Provides: Claude API integration, decision logging,
json parsing, failure recovery, and confidence tracking.
"""

import anthropic
import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime


class BaseAgent(ABC):
      """
          Upgraded base class for all AgentFlow agents.

              UPGRADES FROM ORIGINAL:
                  - Switched from Amazon Bedrock to Anthropic SDK directly
                      - Added decision logging on every call
                          - Added automatic retry with exponential backoff
                              - Added confidence tracking
                                  - Added structured JSON parsing with validation
                                      - Added failure recovery hooks
                                          """

    MODEL = "claude-opus-4-5"
    MAX_TOKENS = 4096
    MAX_RETRIES = 3

    def __init__(self, logger=None, config: dict = None):
              self.client = anthropic.Anthropic()
              self.logger = logger
              self.config = config or {}
              self.call_history = []
              self.total_tokens_used = 0
              self._setup_logging()

    def _setup_logging(self):
              self._log = logging.getLogger(self.__class__.__name__)
              self._log.setLevel(logging.INFO)

    def call_claude(
              self,
              system: str,
              user: str,
              temperature: float = 0.3,
              max_tokens: int = None
    ) -> str:
              """
                      Core method to call Claude API with retry logic.
                              Logs every call for explainability.
                                      """
              start_time = time.time()
              max_tokens = max_tokens or self.MAX_TOKENS

        for attempt in range(self.MAX_RETRIES):
                      try:
                                        response = self.client.messages.create(
                                                              model=self.MODEL,
                                                              max_tokens=max_tokens,
                                                              system=system,
                                                              messages=[{"role": "user", "content": user}]
                                        )

                          content = response.content[0].text
                elapsed = (time.time() - start_time) * 1000

                # Track usage
                self.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens

                # Log the call
                call_record = {
                                      "timestamp": datetime.now().isoformat(),
                                      "agent": self.__class__.__name__,
                                      "attempt": attempt + 1,
                                      "time_ms": round(elapsed, 2),
                                      "input_tokens": response.usage.input_tokens,
                                      "output_tokens": response.usage.output_tokens,
                                      "success": True
                }
                self.call_history.append(call_record)

                if self.logger:
                                      self.logger.log_api_call(call_record)

                return content

except anthropic.RateLimitError:
                wait = 2 ** attempt
                self._log.warning(f"Rate limit hit, waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)

except anthropic.APIError as e:
                self._log.error(f"API error on attempt {attempt+1}: {e}")
                if attempt == self.MAX_RETRIES - 1:
                                      return self.handle_failure(str(e))
                                  time.sleep(1)

        return self.handle_failure("Max retries exceeded")

    def parse_json(self, response: str) -> dict:
              """
                      Safely parse JSON from Claude response.
                              Handles markdown code blocks and malformed JSON.
                                      """
        # Strip markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
                      lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])

        try:
                      return json.loads(cleaned)
except json.JSONDecodeError:
            # Try to extract JSON from text
            import re
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                              try:
                                                    return json.loads(json_match.group())
except json.JSONDecodeError:
                    pass

            self._log.error(f"Failed to parse JSON from response: {response[:200]}")
            return {"error": "JSON_PARSE_FAILED", "raw": response}

    def handle_failure(self, error: str) -> str:
              """
                      Fallback when agent fails. Returns structured error.
                              Subclasses can override for custom recovery.
                                      """
        self._log.error(f"{self.__class__.__name__} failure: {error}")
        return json.dumps({
                      "status": "AGENT_FAILURE",
                      "agent": self.__class__.__name__,
                      "error": error,
                      "timestamp": datetime.now().isoformat()
        })

    def get_stats(self) -> dict:
              """Return performance stats for this agent."""
        return {
                      "agent": self.__class__.__name__,
                      "total_calls": len(self.call_history),
                      "total_tokens": self.total_tokens_used,
                      "avg_time_ms": (
                                        sum(c["time_ms"] for c in self.call_history) / len(self.call_history)
                                        if self.call_history else 0
                      ),
                      "success_rate": (
                                        sum(1 for c in self.call_history if c["success"]) / len(self.call_history)
                                        if self.call_history else 0
                      )
        }
