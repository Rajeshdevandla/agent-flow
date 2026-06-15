"""Constitutional AI Revision Engine

Rewrites outputs that fail the constitutional critique.
Works with self_critique.py to implement the full Constitutional AI loop:
1. Generate initial response
2. Critique against principles
3. Revise if principles violated
4. Repeat up to max_iterations

Reference: Bai et al. (2022) - Constitutional AI: Harmlessness from AI Feedback
"""

import os
import json
from typing import Any
import anthropic


class RevisionEngine:
    """Rewrites AI outputs that violate constitutional principles."""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
        self.revision_history: list[dict[str, Any]] = []

    def revise(
        self,
        original_output: str,
        critique: dict[str, Any],
        task_context: str = ""
    ) -> dict[str, Any]:
        """Revise output based on critique findings.

        Args:
            original_output: The output that needs revision
            critique: The critique result from SelfCritique
            task_context: Original task for context

        Returns:
            Dict with revised output and revision metadata
        """
        violations = critique.get("violations", [])
        issues = critique.get("issues", [])

        if not violations and not issues:
            return {
                "revised_output": original_output,
                "revision_needed": False,
                "changes_made": []
            }

        # Build revision prompt
        issues_text = "\n".join([
            f"- {issue}" for issue in issues
        ]) if issues else "No specific issues listed"

        violations_text = ", ".join(violations) if violations else "none"

        revision_prompt = (
            "The following AI response has issues that need to be fixed.\n\n"
            f"Original task: {task_context}\n\n"
            f"Original response:\n{original_output}\n\n"
            f"Issues found:\n{issues_text}\n\n"
            f"Constitutional principles violated: {violations_text}\n\n"
            "Please rewrite the response to:\n"
            "1. Fix all identified issues\n"
            "2. Maintain factual accuracy\n"
            "3. Keep the same helpful intent\n"
            "4. Be honest about limitations\n\n"
            "Return JSON: {\n"
            "  \"revised_response\": \"...\",\n"
            "  \"changes_made\": [\"change 1\", \"change 2\"],\n"
            "  \"reasoning\": \"why these changes fix the issues\"\n"
            "}"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=(
                    "You are a constitutional AI revision assistant. "
                    "Your job is to rewrite responses that violate ethical principles "
                    "while maintaining their helpful intent and factual accuracy. "
                    "Always return valid JSON."
                ),
                messages=[{"role": "user", "content": revision_prompt}]
            )

            result_text = response.content[0].text

            # Parse JSON response
            try:
                # Find JSON in response
                start = result_text.find("{")
                end = result_text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(result_text[start:end])
                else:
                    result = json.loads(result_text)
            except json.JSONDecodeError:
                result = {
                    "revised_response": result_text,
                    "changes_made": ["Manual review required - could not parse structured response"],
                    "reasoning": "JSON parsing failed"
                }

            revision_record = {
                "original": original_output[:200] + "..." if len(original_output) > 200 else original_output,
                "violations_addressed": violations,
                "issues_addressed": issues,
                "changes": result.get("changes_made", [])
            }
            self.revision_history.append(revision_record)

            return {
                "revised_output": result.get("revised_response", result_text),
                "revision_needed": True,
                "changes_made": result.get("changes_made", []),
                "reasoning": result.get("reasoning", ""),
                "violations_addressed": violations
            }

        except Exception as e:
            return {
                "revised_output": original_output,
                "revision_needed": True,
                "changes_made": [],
                "error": str(e),
                "note": "Revision failed - returning original output"
            }

    def revise_iteratively(
        self,
        initial_output: str,
        task_context: str,
        max_iterations: int = 3
    ) -> dict[str, Any]:
        """Run the full Constitutional AI revision loop.

        Generates critique, revises, re-critiques, until principles
        are satisfied or max_iterations reached.

        Args:
            initial_output: Starting output to improve
            task_context: Original task for context
            max_iterations: Max revision cycles (default 3)

        Returns:
            Dict with final output and full revision history
        """
        from constitutional.self_critique import SelfCritique

        critiquer = SelfCritique(client=self.client)
        current_output = initial_output
        iterations = []

        for i in range(max_iterations):
            # Step 1: Critique current output
            critique = critiquer.critique(current_output)

            iteration_record = {
                "iteration": i + 1,
                "critique_verdict": critique.get("overall_verdict"),
                "violations": critique.get("violations", []),
                "issues": critique.get("issues", [])
            }

            # Step 2: Check if revision needed
            if critique.get("overall_verdict") == "PASS":
                iteration_record["action"] = "STOPPED_EARLY"
                iterations.append(iteration_record)
                break

            # Step 3: Revise
            revision = self.revise(
                original_output=current_output,
                critique=critique,
                task_context=task_context
            )

            iteration_record["action"] = "REVISED"
            iteration_record["changes_made"] = revision.get("changes_made", [])
            iterations.append(iteration_record)

            current_output = revision["revised_output"]

        return {
            "final_output": current_output,
            "original_output": initial_output,
            "iterations_run": len(iterations),
            "iteration_history": iterations,
            "revision_history": self.revision_history
        }

    def get_revision_summary(self) -> dict[str, Any]:
        """Get summary statistics about revisions made."""
        if not self.revision_history:
            return {"total_revisions": 0}

        all_violations = []
        for rev in self.revision_history:
            all_violations.extend(rev.get("violations_addressed", []))

        violation_counts: dict[str, int] = {}
        for v in all_violations:
            violation_counts[v] = violation_counts.get(v, 0) + 1

        return {
            "total_revisions": len(self.revision_history),
            "most_common_violations": sorted(
                violation_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }
