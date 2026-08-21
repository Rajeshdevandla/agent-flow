# agents/evaluator_agent.py
"""
Evaluator Agent - NEW
Scores the entire workflow performance after task completion.
Generates data for eval reports.
"""

from agents.base_agent import BaseAgent
from datetime import datetime


class EvaluatorAgent(BaseAgent):
    """
    NEW AGENT - Scores the entire workflow performance.
    Measures quality, efficiency, and generates improvement recommendations.
    """

    QUALITY_SYSTEM_PROMPT = """
    You are an Evaluator Agent that scores AI system performance.
    Score this response on each dimension from 0-100:
    1. TASK_COMPLETION: Did it answer the actual question?
    2. ACCURACY: Are the facts correct and verifiable?
    3. CLARITY: Is the response clear and readable?
    4. CONCISENESS: Is it the right length without padding?
    5. SAFETY: Is the response safe and appropriate?

    Return as JSON:
    {
      "scores": {"task_completion": 85, "accuracy": 90, "clarity": 80, "conciseness": 75, "safety": 100},
      "total_score": 86,
      "grade": "A|B|C|D|F",
      "strengths": ["what worked well"],
      "weaknesses": ["what needs improvement"],
      "recommendation": "specific improvement suggestion"
    }
    """

    GRADE_THRESHOLDS = {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}

    def run(self, task: str, final_response: str, workflow_results: list) -> dict:
        """Compatibility entry point returning the quality evaluation."""
        result = self.score_quality(task, final_response)
        if "overall" not in result:
            result["overall"] = result.get("total_score", 0)
        return result

    def evaluate_workflow(self, task: str, agent_outputs: list, final_response: str,
                          time_taken_ms: float = 0, tokens_used: int = 0) -> dict:
        """Main evaluation method. Scores the entire workflow run."""
        quality_scores = self.score_quality(task, final_response)
        efficiency_scores = self.score_efficiency(agent_outputs, time_taken_ms, tokens_used)

        quality_avg = sum(quality_scores.get("scores", {}).values()) / max(
            len(quality_scores.get("scores", {})), 1
        )
        efficiency_score = efficiency_scores.get("overall_efficiency", 50)
        total_score = (quality_avg * 0.7) + (efficiency_score * 0.3)

        report = {
            "task": task,
            "timestamp": datetime.now().isoformat(),
            "quality": quality_scores,
            "efficiency": efficiency_scores,
            "total_score": round(total_score, 1),
            "grade": self._score_to_grade(total_score),
            "agents_used": len(agent_outputs),
            "time_taken_ms": time_taken_ms,
            "tokens_used": tokens_used,
            "recommendations": self._generate_recommendations(quality_scores, efficiency_scores)
        }

        if self.logger:
            self.logger.log_decision(
                agent="EvaluatorAgent",
                input=f"Workflow evaluation for: {task[:100]}",
                output=f"Score: {total_score:.1f}/100, Grade: {report['grade']}",
                reasoning="Evaluated quality, efficiency, and safety",
                confidence=0.8, time_taken=0.0
            )

        return report

    def score_quality(self, task: str, response: str) -> dict:
        """Uses Claude to evaluate response quality."""
        result_text = self.call_claude(
            system=self.QUALITY_SYSTEM_PROMPT,
            user=f"Task: {task}\n\nResponse to evaluate:\n{response}"
        )
        result = self.parse_json(result_text)
        if "error" in result:
            return {"scores": {"task_completion": 50, "accuracy": 50, "clarity": 50,
                               "conciseness": 50, "safety": 100},
                    "total_score": 60, "grade": "C", "strengths": [],
                    "weaknesses": ["Evaluation failed"], "recommendation": "Manual review needed"}
        if "total_score" not in result and "scores" in result:
            scores = result["scores"]
            result["total_score"] = sum(scores.values()) / len(scores)
        if "grade" not in result:
            result["grade"] = self._score_to_grade(result.get("total_score", 0))
        return result

    def score_efficiency(self, agent_outputs: list, time_taken_ms: float, tokens_used: int) -> dict:
        """Calculates efficiency metrics without using Claude."""
        FAST_TIME_MS, SLOW_TIME_MS = 5000, 30000
        LOW_TOKENS, HIGH_TOKENS = 1000, 10000

        time_score = max(0, min(100, 100 - (time_taken_ms - FAST_TIME_MS) /
                                (SLOW_TIME_MS - FAST_TIME_MS) * 100)) if time_taken_ms > FAST_TIME_MS else 100
        token_score = max(0, min(100, 100 - (tokens_used - LOW_TOKENS) /
                                 (HIGH_TOKENS - LOW_TOKENS) * 100)) if tokens_used > LOW_TOKENS else 100
        agent_count = len(agent_outputs)
        coordination_score = 100 if agent_count <= 3 else (80 if agent_count <= 6 else 60)
        overall = (time_score + token_score + coordination_score) / 3

        return {"time_score": round(time_score, 1), "token_score": round(token_score, 1),
                "coordination_score": round(coordination_score, 1),
                "overall_efficiency": round(overall, 1), "time_taken_ms": time_taken_ms,
                "tokens_used": tokens_used, "agents_used": agent_count}

    def _score_to_grade(self, score: float) -> str:
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"

    def _generate_recommendations(self, quality: dict, efficiency: dict) -> list:
        recommendations = []
        for dimension, score in quality.get("scores", {}).items():
            if score < 70:
                recommendations.append(f"Improve {dimension.replace('_', ' ')}: score {score}/100")
        if efficiency.get("time_score", 100) < 60:
            recommendations.append("Optimize agent pipeline - response time is slow")
        return recommendations
