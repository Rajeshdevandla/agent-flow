# agents/critic_agent.py
"""
Critic Agent - NEW
Reviews other agents' output before it reaches the user.

This is what makes AgentFlow special and Anthropic-relevant.
The Critic checks every response for accuracy, completeness,
consistency, clarity, and safety before showing it to users.
"""

from agents.base_agent import BaseAgent
import json


class CriticAgent(BaseAgent):
    """
    NEW AGENT - Reviews AI-generated content for quality and accuracy.

    ROLE: Reviews every other agent's output before it reaches the user.

    Checks for:
    - Factual errors or hallucinations
    - Logical inconsistencies
    - Missing important information
    - Tone/safety issues
    - Whether the output actually answers the user's question
    """

    SYSTEM_PROMPT = """
    You are a Critic Agent that reviews AI-generated content for quality.

    For every response you review, check:

    1. ACCURACY - Are all facts verifiable?
       Flag anything that seems made up or unverifiable.

    2. COMPLETENESS - Does it fully answer the user's question?
       What important aspects are missing?

    3. CONSISTENCY - Does it contradict itself or the source material?
       Note any internal contradictions.

    4. CLARITY - Is it actually understandable?
       Would the target audience understand this?

    5. SAFETY - Could this response cause harm if acted upon?
       Flag any potentially harmful guidance.

    Return a structured critique as JSON:
    {
      "verdict": "PASS|NEEDS_REVISION|FAIL",
      "scores": {
        "accuracy": 85,
        "completeness": 90,
        "consistency": 95,
        "clarity": 80,
        "safety": 100
      },
      "overall_score": 90,
      "issues": [
        {
          "category": "ACCURACY|COMPLETENESS|CONSISTENCY|CLARITY|SAFETY",
          "description": "specific problem found",
          "severity": "LOW|MEDIUM|HIGH",
          "suggestion": "how to fix this"
        }
      ],
      "strengths": ["what the response does well"],
      "revision_needed": false,
      "revision_instructions": "specific instructions if revision needed",
      "confidence": 85
    }

    Be harsh but fair. A PASS means you would stake your reputation
    on this response. NEEDS_REVISION means fixable issues exist.
    FAIL means fundamental problems that require starting over.
    """

    PASS_THRESHOLD = 75  # Minimum score to pass
    REVISION_THRESHOLD = 50  # Below this = FAIL, above = NEEDS_REVISION

    def critique(self, response: str, original_task: str) -> dict:
        """
        Reviews an agent's response against the original task.
        Returns structured critique with verdict and specific issues.
        """
        result = self.call_claude(
            system=self.SYSTEM_PROMPT,
            user=f"""Original task: {original_task}

Response to review:
{response}

Provide a thorough critique."""
        )

        critique = self.parse_json(result)

        if "error" in critique:
            return {
                "verdict": "NEEDS_REVISION",
                "scores": {"accuracy": 50, "completeness": 50,
                           "consistency": 50, "clarity": 50, "safety": 100},
                "overall_score": 50,
                "issues": [{"category": "ACCURACY", "description": "Critique failed to parse",
                             "severity": "LOW", "suggestion": "Manual review needed"}],
                "strengths": [],
                "revision_needed": True,
                "revision_instructions": "Review manually - automated critique failed",
                "confidence": 0
            }

        # Calculate overall score if not provided
        if "overall_score" not in critique:
            scores = critique.get("scores", {})
            if scores:
                critique["overall_score"] = sum(scores.values()) / len(scores)

        # Set verdict based on score if not provided
        if "verdict" not in critique:
            score = critique.get("overall_score", 0)
            if score >= self.PASS_THRESHOLD:
                critique["verdict"] = "PASS"
            elif score >= self.REVISION_THRESHOLD:
                critique["verdict"] = "NEEDS_REVISION"
            else:
                critique["verdict"] = "FAIL"

        if self.logger:
            self.logger.log_decision(
                agent="CriticAgent",
                input=f"Review of response to: {original_task[:100]}",
                output=f"Verdict: {critique.get('verdict')}, Score: {critique.get('overall_score')}",
                reasoning=f"{len(critique.get('issues', []))} issues found",
                confidence=critique.get("confidence", 0) / 100.0,
                time_taken=0.0
            )

        return critique

    def should_revise(self, critique_result: dict) -> bool:
        """Returns True if the response needs revision based on critique."""
        verdict = critique_result.get("verdict", "PASS")
        return verdict in ["NEEDS_REVISION", "FAIL"]

    def get_revision_instructions(self, critique_result: dict) -> str:
        """Extracts actionable revision instructions from critique."""
        if not self.should_revise(critique_result):
            return ""

        instructions = critique_result.get("revision_instructions", "")
        issues = critique_result.get("issues", [])

        if issues and not instructions:
            issue_list = []
            for issue in issues:
                severity = issue.get("severity", "")
                desc = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                issue_list.append(f"[{severity}] {desc}. Fix: {suggestion}")
            instructions = "\n".join(issue_list)

        return instructions
