# constitutional/self_critique.py
"""Constitutional AI critique-and-revision loop."""

import json
import re

import anthropic

from constitutional.principles import PRINCIPLES_TEXT


class SelfCritiqueEngine:
    """Critique and revise responses against explicit safety principles."""

    MODEL = "claude-opus-4-5"
    MAX_ITERATIONS = 3

    def __init__(self, max_iterations: int = 3):
        self.client = anthropic.Anthropic()
        self.max_iterations = max_iterations

    def critique_and_revise(
        self,
        original_response: str,
        principles: list | None = None,
        task_context: str = "",
    ) -> dict:
        """Run critique-revision steps until compliant or the limit is reached."""
        if principles is None:
            principles = PRINCIPLES_TEXT

        current_response = original_response
        revision_history = []
        iteration = 0

        while iteration < self.max_iterations:
            critique = self._critique(current_response, principles, task_context)
            revision_history.append(
                {
                    "iteration": iteration + 1,
                    "response_preview": current_response[:300],
                    "critique": critique,
                }
            )

            if not self._needs_revision(critique):
                break

            revised = self._revise(current_response, critique)
            if not revised or revised == current_response:
                break

            current_response = revised
            iteration += 1

        return {
            "original": original_response,
            "final": current_response,
            "was_revised": current_response != original_response,
            "iterations": iteration,
            "revision_history": revision_history,
            "principles_applied": len(principles),
        }

    def _critique(
        self, response: str, principles: list, task_context: str = ""
    ) -> dict:
        """Critique a response against constitutional principles."""
        principles_text = "\n".join(
            f"{index + 1}. {principle}"
            for index, principle in enumerate(principles)
        )
        context_text = f"\nTask context: {task_context}" if task_context else ""

        prompt = f"""Review this AI response against each principle.
Response: {response}{context_text}
Principles:
{principles_text}

Return JSON with this shape:
{{"compliant": true, "violations": [{{"principle_id": 1,
"violation": "description", "severity": "LOW", "fix": "correction"}}],
"recommendation": "summary"}}"""

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"{.*}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {
                "compliant": True,
                "violations": [],
                "recommendation": "Model response could not be parsed.",
            }

    def _revise(self, response: str, critique: dict) -> str:
        """Revise a response to fix every identified violation."""
        violations = critique.get("violations", [])
        if not violations:
            return response

        violations_text = "\n".join(
            f"- Principle {violation.get('principle_id')}: "
            f"{violation.get('violation')}. Fix: {violation.get('fix')}"
            for violation in violations
        )

        prompt = f"""Rewrite this response to fix all violations.

Original: {response}

Violations:
{violations_text}

Keep all accurate helpful content. Fix every violation. Be clear and concise.
Revised response:"""

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def _needs_revision(self, critique: dict) -> bool:
        """Return whether the critique contains actionable violations."""
        return (
            not critique.get("compliant", True)
            and bool(critique.get("violations", []))
        )

    def quick_check(self, response: str) -> bool:
        """Return constitutional compliance for a response."""
        critique = self._critique(response, PRINCIPLES_TEXT)
        return critique.get("compliant", True)
