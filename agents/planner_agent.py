# agents/planner_agent.py
"""
Planner Agent - Upgraded
Breaks down complex user tasks into ordered subtasks for other agents.
"""

from agents.base_agent import BaseAgent
import json


class PlannerAgent(BaseAgent):
      """
          ROLE: Breaks down complex user tasks into ordered subtasks.

              UPGRADES FROM ORIGINAL:
                  - Logs every planning decision with reasoning
                      - Validates plan before passing to next agent
                          - Has fallback plan if primary plan fails
                              - Estimates confidence score for each plan step
                                  """

    SYSTEM_PROMPT = """
        You are a Planning Agent responsible for breaking down
            complex tasks into clear, ordered steps.

                For every plan you create:
                    1. List each step clearly and in order
                        2. Assign which agent should handle each step
                            3. Identify dependencies between steps
                                4. Flag any steps that could fail and why
                                    5. Rate your confidence in this plan (0-100)

                                        Return your response as structured JSON only.
                                            Never skip the confidence rating.
                                                Never create more than 7 steps for any task.

                                                    Required JSON format:
                                                        {
                                                              "task": "original task description",
                                                                    "steps": [
                                                                            {
                                                                                      "step_number": 1,
                                                                                                "action": "description of what to do",
                                                                                                          "agent": "AgentName",
                                                                                                                    "depends_on": [],
                                                                                                                              "risk": "potential failure reason or null",
                                                                                                                                        "estimated_time_seconds": 10
                                                                                                                                                }
                                                                                                                                                      ],
                                                                                                                                                            "confidence": 85,
                                                                                                                                                                  "estimated_total_time_seconds": 45,
                                                                                                                                                                        "complexity": "LOW|MEDIUM|HIGH",
                                                                                                                                                                              "reasoning": "why you structured the plan this way"
    }
        """

    def plan(self, user_task: str) -> dict:
              """Main planning method. Creates an ordered execution plan."""
              if self.logger:
                            self.logger.log_decision(
                                              agent="PlannerAgent",
                                              input=user_task,
                                              output="generating plan...",
                                              reasoning="Breaking task into subtasks",
                                              confidence=0.0,
                                              time_taken=0.0
                            )

              response = self.call_claude(
                  system=self.SYSTEM_PROMPT,
                  user=f"Create a plan for: {user_task}"
              )

        plan = self.parse_json(response)

        if "error" in plan:
                      return self.create_fallback_plan(user_task)

        confidence = plan.get("confidence", 0)
        if confidence < 50:
                      return self.create_fallback_plan(user_task)

        if self.logger:
                      self.logger.log_decision(
                                        agent="PlannerAgent",
                                        input=user_task,
                                        output=json.dumps(plan),
                                        reasoning=plan.get("reasoning", "Plan created successfully"),
                                        confidence=confidence / 100.0,
                                        time_taken=0.0
                      )

        return plan

    def create_fallback_plan(self, user_task: str) -> dict:
              """Creates a simple 2-step fallback plan when primary planning fails."""
              return {
                  "task": user_task,
                  "steps": [
                      {
                          "step_number": 1,
                          "action": f"Research information about: {user_task}",
                          "agent": "ResearcherAgent",
                          "depends_on": [],
                          "risk": "May have incomplete information",
                          "estimated_time_seconds": 15
                      },
                      {
                          "step_number": 2,
                          "action": "Summarize research findings into clear response",
                          "agent": "SummarizerAgent",
                          "depends_on": [1],
                          "risk": None,
                          "estimated_time_seconds": 10
                      }
                  ],
                  "confidence": 40,
                  "estimated_total_time_seconds": 25,
                  "complexity": "LOW",
                  "reasoning": "Fallback plan - primary planning failed",
                  "is_fallback": True
              }

    def validate_plan(self, plan: dict) -> tuple:
              """Validates a plan before execution. Returns (is_valid, issues)."""
              issues = []
              if not plan.get("steps"):
                            issues.append("Plan has no steps")
                        if len(plan.get("steps", [])) > 7:
                                      issues.append("Plan exceeds maximum 7 steps")
                                  if plan.get("confidence", 0) < 30:
                                                issues.append(f"Confidence too low: {plan.get('confidence')}")
                                            for step in plan.get("steps", []):
                                                          if not step.get("agent"):
                                                                            issues.append(f"Step {step.get('step_number')} missing agent")
                                                                    return len(issues) == 0, issues
