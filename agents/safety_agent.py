"""Constitutional safety agent for reviewing generated content."""

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
        if "error" in result:
            return {
                "action": "WARN_USER",
                "issues": ["Safety review could not be parsed"],
                "score": 50,
                "violations": [],
            }
        return result
