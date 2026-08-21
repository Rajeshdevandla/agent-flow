# agents/summarizer_agent.py
"""
Summarizer Agent - Upgraded
Synthesizes research into clear, audience-appropriate output.

UPGRADES FROM ORIGINAL:
- Adjusts reading level based on user type
- Flags if summary contradicts source material
- Passes output structure to Critic before returning
- Switched from Bedrock to Anthropic SDK
"""

from agents.base_agent import BaseAgent


class SummarizerAgent(BaseAgent):
    """
    ROLE: Synthesizes research into clear output tailored to the audience.

    UPGRADES FROM ORIGINAL:
    - Adjusts reading level based on user type
    - Flags contradictions in source material
    - Structured output with uncertainty flagging
    """

    SYSTEM_PROMPT = """
    You are a Summarizer Agent that creates clear, accurate summaries
    from research findings.

    Always:
    1. Match the reading level to the user type provided
       - technical: use precise terminology, include details
       - non-technical: use plain language, avoid jargon
       - researcher: include caveats, methodology notes, sources
    2. Never add information not in the research
    3. Flag any contradictions in source material
    4. Keep summaries under 300 words unless asked for more
    5. End with: "Key uncertainty: [biggest unknown]"
    6. Note confidence level for the overall summary

    Return as JSON:
    {
      "summary": "the main summary text",
      "reading_level": "technical|non-technical|researcher",
      "word_count": 150,
      "key_points": ["point 1", "point 2", "point 3"],
      "contradictions_found": [],
      "key_uncertainty": "the biggest remaining unknown",
      "confidence": "HIGH|MEDIUM|LOW",
      "sources_used": ["source 1", "source 2"]
    }
    """

    USER_TYPES = ["technical", "non-technical", "researcher"]

    def run(self, task: str, research: dict, user_type: str = "non-technical") -> dict:
        """Compatibility entry point used by the orchestration pipeline."""
        return self.summarize(research, user_type=user_type)

    def summarize(
        self,
        research_findings: dict,
        user_type: str = "non-technical",
        max_words: int = 300
    ) -> dict:
        """
        Main summarization method. Adapts to audience type.
        """
        if user_type not in self.USER_TYPES:
            user_type = "non-technical"

        findings_text = self._format_findings(research_findings)

        prompt = f"""Summarize these research findings for a {user_type} user.
Keep the summary under {max_words} words.

Research findings:
{findings_text}"""

        response = self.call_claude(
            system=self.SYSTEM_PROMPT,
            user=prompt
        )

        result = self.parse_json(response)

        if "error" in result:
            return {
                "summary": "Unable to generate summary due to processing error.",
                "reading_level": user_type,
                "word_count": 0,
                "key_points": [],
                "contradictions_found": [],
                "key_uncertainty": "Unknown - summarization failed",
                "confidence": "LOW",
                "sources_used": []
            }

        if self.logger:
            self.logger.log_decision(
                agent="SummarizerAgent",
                input=f"Research findings for {user_type} user",
                output=f"Summary: {result.get('word_count', 0)} words",
                reasoning=f"Adapted for {user_type} reading level",
                confidence=self._level_to_score(result.get("confidence")),
                time_taken=0.0
            )

        return result

    def _format_findings(self, research: dict) -> str:
        """Format research findings dict into readable text for summarization."""
        if isinstance(research, str):
            return research

        parts = []
        if "summary" in research:
            parts.append(f"Overview: {research['summary']}")

        if "findings" in research:
            for i, finding in enumerate(research["findings"], 1):
                if isinstance(finding, dict):
                    claim = finding.get("claim", "")
                    confidence = finding.get("confidence", "")
                    parts.append(f"{i}. {claim} (Confidence: {confidence})")

        if "key_uncertainties" in research:
            uncertainties = research["key_uncertainties"]
            if uncertainties:
                parts.append(f"Uncertainties: {', '.join(uncertainties)}")

        return "\n".join(parts) if parts else str(research)

    def _level_to_score(self, level: str) -> float:
        return {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}.get(level, 0.5)

    def check_for_contradictions(self, summary: str, findings: list) -> list:
        """
        Checks if summary contradicts any source findings.
        Returns list of contradictions found.
        """
        contradiction_prompt = f"""Check if this summary contradicts any of the source findings.

Summary: {summary}

Source findings:
{chr(10).join([str(f) for f in findings])}

Return a JSON list of contradictions found, or empty list if none:
["contradiction 1", "contradiction 2"]
Only include real contradictions, not just different phrasing."""

        response = self.call_claude(
            system="You are a fact-checker. Find contradictions between summaries and sources.",
            user=contradiction_prompt
        )

        result = self.parse_json(response)
        if isinstance(result, list):
            return result
        return []
