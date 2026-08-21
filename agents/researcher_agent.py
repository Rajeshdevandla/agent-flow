"""Research agent that produces structured findings and uncertainty notes."""

import json

from agents.base_agent import BaseAgent


class ResearcherAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are a research agent. Return JSON with findings, data_quality,
key_uncertainties, and insufficient_data. Clearly separate facts from uncertainty.
"""

    def run(self, task: str, plan: dict) -> dict:
        return self.research(task, plan)

    def research(self, task: str, plan: dict) -> dict:
        response = self.call_claude(
            system=self.SYSTEM_PROMPT,
            user=f"Task: {task}\nPlan: {json.dumps(plan)}",
        )
        result = self.parse_json(response)
        if "error" in result:
            return {
                "findings": [],
                "data_quality": "LOW",
                "key_uncertainties": ["Research response could not be parsed"],
                "insufficient_data": True,
                "reason": "INSUFFICIENT_DATA",
            }
        return result
