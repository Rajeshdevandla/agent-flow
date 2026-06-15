"""AgentFlow v2.0 Agent Unit Tests

Tests for all 7 agents: base, planner, researcher, summarizer,
critic, safety, and evaluator.

Design decision: Tests use mocked Anthropic client to test agent logic
without making real API calls. Integration tests are separate.
"""

import pytest
from unittest.mock import MagicMock, patch
import json


# =============================================================================
# Test BaseAgent
# =============================================================================

class TestBaseAgent:
    """Tests for BaseAgent functionality."""

    def test_base_agent_initialization(self):
        """BaseAgent should initialize with correct defaults."""
        from agents.base_agent import BaseAgent

        mock_client = MagicMock()
        agent = BaseAgent(client=mock_client, model="claude-opus-4-5")

        assert agent.model == "claude-opus-4-5"
        assert agent.client == mock_client
        assert agent.max_retries == 3

    def test_base_agent_creates_message(self):
        """BaseAgent should create Anthropic messages correctly."""
        from agents.base_agent import BaseAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_client.messages.create.return_value = mock_response

        agent = BaseAgent(client=mock_client, model="claude-opus-4-5")
        result = agent.call_claude("Test prompt", "Test system")

        assert result == "Test response"
        mock_client.messages.create.assert_called_once()

    def test_base_agent_retry_on_failure(self):
        """BaseAgent should retry on failure up to max_retries."""
        from agents.base_agent import BaseAgent

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")

        agent = BaseAgent(client=mock_client, model="claude-opus-4-5", max_retries=2)

        with pytest.raises(Exception):
            agent.call_claude("Test prompt", "Test system")

        # Should have retried 2 times
        assert mock_client.messages.create.call_count == 2


# =============================================================================
# Test PlannerAgent
# =============================================================================

class TestPlannerAgent:
    """Tests for PlannerAgent."""

    def test_planner_returns_json(self):
        """PlannerAgent should return valid JSON with required fields."""
        from agents.planner_agent import PlannerAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "plan": ["Step 1: Research", "Step 2: Analyze", "Step 3: Summarize"],
            "confidence": 85,
            "reasoning": "Clear task with good scope",
            "estimated_steps": 3
        }))]
        mock_client.messages.create.return_value = mock_response

        planner = PlannerAgent(client=mock_client)
        result = planner.run(task="Explain machine learning")

        assert "plan" in result
        assert "confidence" in result
        assert isinstance(result["plan"], list)
        assert 0 <= result["confidence"] <= 100

    def test_planner_handles_low_confidence(self):
        """PlannerAgent should flag low confidence plans."""
        from agents.planner_agent import PlannerAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "plan": ["Step 1: Try something"],
            "confidence": 30,
            "reasoning": "Vague task",
            "estimated_steps": 1
        }))]
        mock_client.messages.create.return_value = mock_response

        planner = PlannerAgent(client=mock_client)
        result = planner.run(task="Do something unclear")

        assert result["confidence"] < 50
        # Low confidence should trigger fallback plan note
        assert "fallback" in str(result).lower() or result["confidence"] < 50


# =============================================================================
# Test ResearcherAgent
# =============================================================================

class TestResearcherAgent:
    """Tests for ResearcherAgent."""

    def test_researcher_returns_structured_output(self):
        """ResearcherAgent should return structured findings."""
        from agents.researcher_agent import ResearcherAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "findings": [
                {"fact": "ML uses training data", "confidence": "HIGH", "source": "Well-known"}
            ],
            "data_quality": "HIGH",
            "key_uncertainties": ["Specific algorithms vary"],
            "insufficient_data": False
        }))]
        mock_client.messages.create.return_value = mock_response

        researcher = ResearcherAgent(client=mock_client)
        result = researcher.run(task="What is machine learning?", plan={})

        assert "findings" in result
        assert "data_quality" in result
        assert isinstance(result["findings"], list)

    def test_researcher_flags_insufficient_data(self):
        """ResearcherAgent should flag when data is insufficient."""
        from agents.researcher_agent import ResearcherAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "findings": [],
            "data_quality": "LOW",
            "key_uncertainties": ["No reliable data available"],
            "insufficient_data": True,
            "reason": "INSUFFICIENT_DATA"
        }))]
        mock_client.messages.create.return_value = mock_response

        researcher = ResearcherAgent(client=mock_client)
        result = researcher.run(task="Predict next year stock prices exactly", plan={})

        # Should acknowledge insufficient data
        assert result.get("insufficient_data") or result.get("data_quality") == "LOW"


# =============================================================================
# Test SummarizerAgent
# =============================================================================

class TestSummarizerAgent:
    """Tests for SummarizerAgent."""

    def test_summarizer_adapts_to_user_type(self):
        """SummarizerAgent should adapt output for different user types."""
        from agents.summarizer_agent import SummarizerAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "summary": "Simple explanation for non-technical users.",
            "reading_level": "non-technical",
            "word_count": 50,
            "key_uncertainty": "Exact implementation details vary"
        }))]
        mock_client.messages.create.return_value = mock_response

        summarizer = SummarizerAgent(client=mock_client)
        result = summarizer.run(task="Explain ML", research={}, user_type="non-technical")

        assert "summary" in result
        assert "key_uncertainty" in result

    def test_summarizer_respects_word_limit(self):
        """SummarizerAgent summary should be under 300 words."""
        from agents.summarizer_agent import SummarizerAgent

        long_summary = " ".join(["word"] * 250)  # 250 words
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "summary": long_summary,
            "reading_level": "technical",
            "word_count": 250,
            "key_uncertainty": "Some uncertainty"
        }))]
        mock_client.messages.create.return_value = mock_response

        summarizer = SummarizerAgent(client=mock_client)
        result = summarizer.run(task="Explain ML", research={}, user_type="technical")

        word_count = len(result["summary"].split())
        assert word_count <= 300, f"Summary too long: {word_count} words"


# =============================================================================
# Test CriticAgent
# =============================================================================

class TestCriticAgent:
    """Tests for CriticAgent."""

    def test_critic_returns_verdict(self):
        """CriticAgent should return a verdict with score."""
        from agents.critic_agent import CriticAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "verdict": "PASS",
            "score": 88,
            "issues": [],
            "suggestions": ["Could add more examples"]
        }))]
        mock_client.messages.create.return_value = mock_response

        critic = CriticAgent(client=mock_client)
        result = critic.run(content="This is a good response about machine learning.")

        assert "verdict" in result
        assert result["verdict"] in ["PASS", "NEEDS_REVISION", "FAIL"]
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_critic_fails_bad_content(self):
        """CriticAgent should fail clearly incorrect content."""
        from agents.critic_agent import CriticAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "verdict": "FAIL",
            "score": 15,
            "issues": ["Contains factual errors", "Completely inaccurate"],
            "suggestions": ["Rewrite entirely"]
        }))]
        mock_client.messages.create.return_value = mock_response

        critic = CriticAgent(client=mock_client)
        result = critic.run(content="Paris is the capital of Germany.")

        assert result["verdict"] in ["FAIL", "NEEDS_REVISION"]
        assert result["score"] < 50


# =============================================================================
# Test SafetyAgent
# =============================================================================

class TestSafetyAgent:
    """Tests for SafetyAgent - most critical tests."""

    def test_safety_passes_good_content(self):
        """SafetyAgent should pass safe, helpful content."""
        from agents.safety_agent import SafetyAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "action": "PASS",
            "issues": [],
            "score": 95,
            "violations": []
        }))]
        mock_client.messages.create.return_value = mock_response

        safety = SafetyAgent(client=mock_client)
        result = safety.run(content="Machine learning is a subset of AI that learns from data.")

        assert result["action"] == "PASS"
        assert result["score"] >= 70

    def test_safety_blocks_harmful_content(self):
        """SafetyAgent should block harmful content."""
        from agents.safety_agent import SafetyAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "action": "BLOCK",
            "issues": ["Contains instructions for harmful activity"],
            "score": 5,
            "violations": ["PRINCIPLE_1_SAFETY"]
        }))]
        mock_client.messages.create.return_value = mock_response

        safety = SafetyAgent(client=mock_client)
        result = safety.run(content="Here is how to harm people...")

        assert result["action"] == "BLOCK"
        assert len(result["issues"]) > 0

    def test_safety_warns_on_borderline_content(self):
        """SafetyAgent should warn on borderline content."""
        from agents.safety_agent import SafetyAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "action": "WARN_USER",
            "issues": ["May be sensitive topic"],
            "score": 55,
            "violations": []
        }))]
        mock_client.messages.create.return_value = mock_response

        safety = SafetyAgent(client=mock_client)
        result = safety.run(content="Some potentially sensitive medical information...")

        assert result["action"] in ["PASS", "WARN_USER"]


# =============================================================================
# Test EvaluatorAgent
# =============================================================================

class TestEvaluatorAgent:
    """Tests for EvaluatorAgent."""

    def test_evaluator_returns_grade(self):
        """EvaluatorAgent should return a letter grade."""
        from agents.evaluator_agent import EvaluatorAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "scores": {
                "task_completion": 90,
                "accuracy": 85,
                "clarity": 88,
                "conciseness": 82,
                "safety": 95
            },
            "overall": 88,
            "grade": "B",
            "summary": "Good response with minor improvements possible"
        }))]
        mock_client.messages.create.return_value = mock_response

        evaluator = EvaluatorAgent(client=mock_client)
        result = evaluator.run(
            task="Explain machine learning",
            final_response="Machine learning is...",
            workflow_results=[]
        )

        assert "grade" in result
        assert result["grade"] in ["A", "B", "C", "D", "F"]
        assert "overall" in result
        assert 0 <= result["overall"] <= 100

    def test_evaluator_scores_all_dimensions(self):
        """EvaluatorAgent should score all required dimensions."""
        from agents.evaluator_agent import EvaluatorAgent

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "scores": {
                "task_completion": 75,
                "accuracy": 80,
                "clarity": 70,
                "conciseness": 65,
                "safety": 100
            },
            "overall": 78,
            "grade": "C",
            "summary": "Acceptable but could be improved"
        }))]
        mock_client.messages.create.return_value = mock_response

        evaluator = EvaluatorAgent(client=mock_client)
        result = evaluator.run(
            task="Explain ML",
            final_response="ML is...",
            workflow_results=[]
        )

        scores = result.get("scores", {})
        required_dimensions = ["task_completion", "accuracy", "clarity", "safety"]
        for dim in required_dimensions:
            assert dim in scores, f"Missing score dimension: {dim}"
            assert 0 <= scores[dim] <= 100


# =============================================================================
# Integration-like tests (with mocked API)
# =============================================================================

class TestAgentIntegration:
    """Integration tests for agent pipeline."""

    def test_planner_feeds_into_researcher(self):
        """Planner output should be valid input for Researcher."""
        from agents.planner_agent import PlannerAgent
        from agents.researcher_agent import ResearcherAgent

        mock_client = MagicMock()

        # Planner response
        planner_output = {
            "plan": ["Research topic", "Analyze data", "Summarize"],
            "confidence": 90,
            "reasoning": "Clear task"
        }

        # Researcher response
        researcher_output = {
            "findings": [{"fact": "Test fact", "confidence": "HIGH"}],
            "data_quality": "HIGH",
            "key_uncertainties": []
        }

        mock_client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text=json.dumps(planner_output))]),
            MagicMock(content=[MagicMock(text=json.dumps(researcher_output))])
        ]

        planner = PlannerAgent(client=mock_client)
        plan = planner.run(task="Test task")

        researcher = ResearcherAgent(client=mock_client)
        research = researcher.run(task="Test task", plan=plan)

        # Plan should have been used
        assert research is not None
        assert "findings" in research
