"""Planning agent that turns a task into a structured execution plan."""

import json

from agents.base_agent import BaseAgent


class PlannerAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are a planning agent. Return JSON containing a plan, confidence,
reasoning, and estimated_steps. Keep the plan ordered and under seven steps.
"""

    def run(self, task: str) -> dict:
        return self.plan(task)

    def plan(self, user_task: str) -> dict:
        if self.logger:
            self.logger.log_decision(
                agent="PlannerAgent",
                input=user_task,
                output="generating plan...",
                reasoning="Breaking task into subtasks",
                confidence=0.0,
                time_taken=0.0,
            )

        response = self.call_claude(
            system=self.SYSTEM_PROMPT,
            user=f"Create a plan for: {user_task}",
        )
        plan = self.parse_json(response)
        if "error" in plan:
            return self.create_fallback_plan(user_task)

        if self.logger:
            self.logger.log_decision(
                agent="PlannerAgent",
                input=user_task,
                output=json.dumps(plan),
                reasoning=plan.get("reasoning", "Plan created successfully"),
                confidence=plan.get("confidence", 0) / 100.0,
                time_taken=0.0,
            )
        return plan

    def create_fallback_plan(self, user_task: str) -> dict:
        return {
            "task": user_task,
            "plan": [
                f"Research information about: {user_task}",
                "Summarize the findings into a clear response",
            ],
            "confidence": 40,
            "estimated_steps": 2,
            "reasoning": "Fallback plan used because the primary plan could not be parsed",
            "is_fallback": True,
        }

    def validate_plan(self, plan: dict) -> tuple:
        issues = []
        steps = plan.get("plan", plan.get("steps", []))
        if not steps:
            issues.append("Plan has no steps")
        if len(steps) > 7:
            issues.append("Plan exceeds maximum 7 steps")
        if plan.get("confidence", 0) < 30:
            issues.append(f"Confidence too low: {plan.get('confidence')}")
        return len(issues) == 0, issues
