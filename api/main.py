"""AgentFlow v2.0 FastAPI Server

REST API for the AgentFlow multi-agent system.
Design decision: FastAPI chosen for async support, automatic OpenAPI docs,
and type validation with Pydantic.
"""

import os
import time
from typing import Any

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.planner_agent import PlannerAgent
from agents.researcher_agent import ResearcherAgent
from agents.summarizer_agent import SummarizerAgent
from agents.critic_agent import CriticAgent
from agents.safety_agent import SafetyAgent
from agents.evaluator_agent import EvaluatorAgent
from orchestrator.workflow_engine import WorkflowEngine
from orchestrator.decision_logger import DecisionLogger


# Initialize FastAPI
app = FastAPI(
    title="AgentFlow v2.0 API",
    description="Multi-agent AI workflow system powered by Anthropic Claude",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================================
# Request/Response Models
# =========================================================================

class WorkflowRequest(BaseModel):
    """Request to run the full 6-agent workflow."""
    task: str
    user_type: str = "technical"  # technical, non-technical, researcher
    enable_critic: bool = True
    enable_safety: bool = True
    enable_evaluator: bool = True


class AgentResult(BaseModel):
    """Result from a single agent."""
    agent_name: str
    status: str
    output: dict[str, Any]
    duration: float
    tokens_used: int


class WorkflowResponse(BaseModel):
    """Full workflow response."""
    task: str
    final_response: str
    agent_results: list[AgentResult]
    safety_report: dict[str, Any]
    quality_scores: dict[str, Any]
    total_duration: float
    total_tokens: int
    workflow_id: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    anthropic_connected: bool
    agents_available: list[str]


# =========================================================================
# Initialize agents
# =========================================================================

def get_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# =========================================================================
# Routes
# =========================================================================

@app.get("/", summary="API Root")
async def root():
    """AgentFlow API root endpoint."""
    return {
        "name": "AgentFlow v2.0 API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse, summary="Health Check")
async def health_check():
    """Check API and Anthropic connection health."""
    agents_available = [
        "PlannerAgent",
        "ResearcherAgent",
        "SummarizerAgent",
        "CriticAgent",
        "SafetyAgent",
        "EvaluatorAgent"
    ]

    # Test Anthropic connection
    anthropic_connected = False
    try:
        client = get_client()
        client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        anthropic_connected = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if anthropic_connected else "degraded",
        version="2.0.0",
        anthropic_connected=anthropic_connected,
        agents_available=agents_available
    )


@app.post("/workflow/run", response_model=WorkflowResponse, summary="Run Full Workflow")
async def run_workflow(request: WorkflowRequest):
    """Run the complete 6-agent workflow on a task.

    Pipeline: PlannerAgent -> ResearcherAgent -> SummarizerAgent
              -> CriticAgent -> SafetyAgent -> EvaluatorAgent
    """
    client = get_client()
    start_time = time.time()
    workflow_id = f"wf_{int(time.time())}"

    logger = DecisionLogger(workflow_id=workflow_id)
    agent_results = []
    total_tokens = 0

    try:
        # Step 1: PlannerAgent
        planner = PlannerAgent(client=client)
        plan_result = planner.run(task=request.task)
        agent_results.append(AgentResult(
            agent_name="PlannerAgent",
            status="complete",
            output=plan_result,
            duration=0.0,
            tokens_used=0
        ))
        logger.log("PlannerAgent", plan_result)

        # Step 2: ResearcherAgent
        researcher = ResearcherAgent(client=client)
        research_result = researcher.run(task=request.task, plan=plan_result)
        agent_results.append(AgentResult(
            agent_name="ResearcherAgent",
            status="complete",
            output=research_result,
            duration=0.0,
            tokens_used=0
        ))
        logger.log("ResearcherAgent", research_result)

        # Step 3: SummarizerAgent
        summarizer = SummarizerAgent(client=client)
        summary_result = summarizer.run(
            task=request.task,
            research=research_result,
            user_type=request.user_type
        )
        agent_results.append(AgentResult(
            agent_name="SummarizerAgent",
            status="complete",
            output=summary_result,
            duration=0.0,
            tokens_used=0
        ))
        logger.log("SummarizerAgent", summary_result)

        final_response_text = summary_result.get("summary", str(summary_result))

        # Step 4: CriticAgent (optional)
        critic_result = {}
        if request.enable_critic:
            critic = CriticAgent(client=client)
            critic_result = critic.run(content=final_response_text)
            agent_results.append(AgentResult(
                agent_name="CriticAgent",
                status="complete",
                output=critic_result,
                duration=0.0,
                tokens_used=0
            ))
            logger.log("CriticAgent", critic_result)

        # Step 5: SafetyAgent (optional but recommended)
        safety_result = {"action": "PASS", "issues": [], "score": 100}
        if request.enable_safety:
            safety = SafetyAgent(client=client)
            safety_result = safety.run(content=final_response_text)
            agent_results.append(AgentResult(
                agent_name="SafetyAgent",
                status="complete",
                output=safety_result,
                duration=0.0,
                tokens_used=0
            ))
            logger.log("SafetyAgent", safety_result)

            # Block if safety fails
            if safety_result.get("action") == "BLOCK":
                raise HTTPException(
                    status_code=400,
                    detail=f"Response blocked by SafetyAgent: {safety_result.get('issues', [])}"
                )

        # Step 6: EvaluatorAgent (optional)
        eval_result = {}
        if request.enable_evaluator:
            evaluator = EvaluatorAgent(client=client)
            eval_result = evaluator.run(
                task=request.task,
                final_response=final_response_text,
                workflow_results=agent_results
            )
            agent_results.append(AgentResult(
                agent_name="EvaluatorAgent",
                status="complete",
                output=eval_result,
                duration=0.0,
                tokens_used=0
            ))
            logger.log("EvaluatorAgent", eval_result)

        total_duration = time.time() - start_time

        return WorkflowResponse(
            task=request.task,
            final_response=final_response_text,
            agent_results=agent_results,
            safety_report=safety_result,
            quality_scores=eval_result,
            total_duration=total_duration,
            total_tokens=total_tokens,
            workflow_id=workflow_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Workflow error: {str(e)}"
        )


@app.get("/agents", summary="List Available Agents")
async def list_agents():
    """List all available agents and their capabilities."""
    return {
        "agents": [
            {
                "name": "PlannerAgent",
                "role": "Creates execution plan with confidence scoring",
                "output_format": "JSON with plan steps and confidence"
            },
            {
                "name": "ResearcherAgent",
                "role": "Gathers and validates information",
                "output_format": "JSON with findings and data quality"
            },
            {
                "name": "SummarizerAgent",
                "role": "Creates audience-appropriate summaries",
                "output_format": "JSON with summary and key uncertainty"
            },
            {
                "name": "CriticAgent",
                "role": "Reviews output for quality",
                "output_format": "JSON with verdict and issues"
            },
            {
                "name": "SafetyAgent",
                "role": "Checks for safety violations",
                "output_format": "JSON with action and safety score"
            },
            {
                "name": "EvaluatorAgent",
                "role": "Scores overall workflow quality",
                "output_format": "JSON with scores and grade"
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true"
    )
