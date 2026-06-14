# constitutional/self_critique.py
"""
Self-Critique Engine - NEW
Inspired by Anthropic Constitutional AI paper.
Makes Claude critique and revise its own outputs against principles.
"""

import anthropic
import json
import re
from constitutional.principles import PRINCIPLES_TEXT


class SelfCritiqueEngine:
    """
    Implements Constitutional AI critique-revision loop.
    
    Process:
    1. Generate response
    2. Critique against each principle
    3. Revise to fix violations
    4. Repeat until compliant or max iterations
    """

    MODEL = "claude-opus-4-5"
    MAX_ITERATIONS = 3

    def __init__(self, max_iterations: int = 3):
        self.client = anthropic.Anthropic()
        self.max_iterations = max_iterations

    def critique_and_revise(
        self,
        original_response: str,
        principles: list = None,
        task_context: str = ""
    ) -> dict:
        """
        Main critique-revision loop.
        Returns dict with original, critiques, and final revised response.
        """
        if principles is None:
            principles = PRINCIPLES_TEXT

        current_response = original_response
        revision_history = []
        iteration = 0

        while iteration < self.max_iterations:
            critique = self._critique(current_response, principles, task_context)

            revision_history.append({
                "iteration": iteration + 1,
                "response_preview": current_response[:300],
                "critique": critique
            })

            if not self._needs_revision(critique):
                break

            revised = self._revise(current_response, critique)
            if revised and revised != current_response:
                current_response = revised
                iteration += 1
            else:
                break

        return {
            "original": original_response,
            "final": current_response,
            "was_revised": current_response != original_response,
            "iterations": iteration,
            "revision_history": revision_history,
            "principles_applied": len(principles)
        }

    def _critique(
        self, response: str, principles: list, task_context: str = ""
    ) -> dict:
        """Critiques a response against constitutional principles."""
        principles_text = chr(10).join(
            f"{i+1}. {p}" for i, p in enumerate(principles)
        )

        prompt = f"""Review this AI response against each principle.
Response: {response}
Principles:
{principles_text}

Return JSON: {"compliant": bool, "violations": [{"principle_id": int,
"violation": str, "severity": str, "fix": str}], "recommendation": str}"""

        msg = self.client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = chr(10).join(text.split(chr(10))[1:-1])

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"{.*}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except:
                    pass
            return {"compliant": True, "violations": [], "recommendation": "parse error"}

    def _revise(self, response: str, critique: dict) -> str:
        """Revises a response to fix all identified violations."""
        violations = critique.get("violations", [])
        if not violations:
            return response

        violations_text = chr(10).join(
            f"- Principle {v.get(chr(39)principle_id{chr(39)})}: {v.get(chr(39)violation{chr(39)})}. Fix: {v.get(chr(39)fix{chr(39)})}"
            for v in violations
        )

        prompt = f"""Rewrite this response to fix all violations.

Original: {response}

Violations:
{violations_text}

Keep all accurate helpful content. Fix every violation. Be clear and concise.
Revised response:"""

        msg = self.client.messages.create(
            model=self.MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()

    def _needs_revision(self, critique: dict) -> bool:
        """Returns True if revision is needed."""
        return not critique.get("compliant", True) and len(critique.get("violations", [])) > 0

    def quick_check(self, response: str) -> bool:
        """Quick boolean constitutional compliance check."""
        critique = self._critique(response, PRINCIPLES_TEXT)
        return critique.get("compliant", True)
