"""Constitutional safety agent for reviewing generated content."""

import math

from agents.base_agent import BaseAgent


class SafetyAgent(BaseAgent):
    SYSTEM_PROMPT = """
Review the content using safety principles. Return JSON with action
(PASS, WARN_USER, or BLOCK), issues, score from 0-100, and violations.
Block content that meaningfully enables harm.
"""

    def run(self, content: str) -> dict:
        return self.review(content)

    def review(self, content: str) -> dict:
        response = self.call_claude(system=self.SYSTEM_PROMPT, user=content)
        result = self.parse_json(response)
        if not self._valid_review(result):
            return {
                "action": "BLOCK",
                "issues": ["Safety review was invalid; response withheld."],
                "score": 0,
                "violations": [],
                "error": "INVALID_SAFETY_REVIEW",
            }
        return result

    @staticmethod
    def get_user_message(result: dict) -> str:
        """Format warning details from a validated safety review for callers."""
        if result.get("action") != "WARN_USER":
            return ""
        details = " ".join(issue.strip() for issue in result["issues"] if issue.strip())
        return "Safety warning: " + (
            details or "Review this response carefully before using it."
        )

    @staticmethod
    def _valid_review(result) -> bool:
        """Only a complete, well-typed review can authorize a response."""
        if not isinstance(result, dict) or "error" in result:
            return False
        if result.get("action") not in ("PASS", "WARN_USER", "BLOCK"):
            return False
        score = result.get("score")
        if type(score) not in (int, float) or not 0 <= score <= 100:
            return False
        if not math.isfinite(score):
            return False
        return all(
            isinstance(result.get(field), list)
            and all(isinstance(item, str) for item in result[field])
            for field in ("issues", "violations")
        )
