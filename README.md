# AgentFlow v2.0

> A multi-agent AI orchestration system built on Anthropic's Claude with Constitutional AI-inspired safety layers, full decision logging, and systematic evaluation framework.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Anthropic Claude](https://img.shields.io/badge/powered%20by-Anthropic%20Claude-orange.svg)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Why I Built This

Most multi-agent systems fail in production for three reasons: they hallucinate confidently, they have no safety checks, and when something goes wrong you have no idea why. AgentFlow v2.0 addresses all three.

The original version used Amazon Bedrock and had three agents. This version uses the Anthropic SDK directly, adds three new agents inspired by Anthropic's research, and implements a Constitutional AI safety layer that checks every response before it reaches the user.

## Architecture

```
USER TASK
     |
     v
[PlannerAgent]     -- Breaks task into steps with confidence score
     |
     v
[ResearcherAgent]  -- Gathers info with citations and confidence levels
     |
     v
[SummarizerAgent]  -- Synthesizes for target audience
     |
     v
[CriticAgent]      -- Reviews quality, loops back if needed (max 2 revisions)
     |
     v
[SafetyAgent]      -- Constitutional AI check, blocks if unsafe
     |
     v
[EvaluatorAgent]   -- Scores the entire workflow
     |
     v
FINAL RESPONSE + Decision Log + Quality Score + Safety Report
```

## The 6 Agents

### 1. PlannerAgent (Upgraded)
Breaks down complex tasks into ordered steps with dependency tracking. Key upgrade: now validates every plan and falls back gracefully if confidence is below 50%. Every planning decision is logged with reasoning.

### 2. ResearcherAgent (Upgraded)
Gathers information with explicit source citations and confidence levels (HIGH/MEDIUM/LOW). Key upgrade: returns `INSUFFICIENT_DATA` instead of hallucinating. Never presents uncertain information as fact.

### 3. SummarizerAgent (Upgraded)
Synthesizes research into clear output tailored to the user type (technical/non-technical/researcher). Key upgrade: detects and flags contradictions in source material before summarizing.

### 4. CriticAgent (NEW)
Reviews every other agent's output before it reaches the user. Checks accuracy, completeness, consistency, clarity, and safety. Returns PASS/NEEDS_REVISION/FAIL with specific issues and fix suggestions. Triggers revision loop up to 2 times.

### 5. SafetyAgent (NEW)
The most important addition. Runs every response through a 10-principle constitutional check inspired by Anthropic's Constitutional AI paper. PASS/WARN_USER/BLOCK based on severity. Every check is logged.

### 6. EvaluatorAgent (NEW)
Scores the entire workflow after completion. Measures task completion, accuracy, clarity, conciseness, and safety (0-100 each). Calculates efficiency metrics and generates improvement recommendations.

## Constitutional AI Layer

The `constitutional/` directory implements a lightweight version of Anthropic's Constitutional AI approach. The `SelfCritiqueEngine` in `constitutional/self_critique.py` makes Claude critique and revise its own outputs based on 10 defined principles:

1. No Physical Harm (CRITICAL)
2. No Manipulation (HIGH)
3. Calibrated Honesty (HIGH)
4. No Impersonation (HIGH)
5. Privacy Respect (HIGH)
6. Equal Treatment (MEDIUM)
7. Capability Transparency (MEDIUM)
8. No Weapon Assistance (CRITICAL)
9. Vulnerable Population Protection (CRITICAL)
10. No Violence Incitement (CRITICAL)

Each principle includes examples of violations and compliance, enabling the safety agent to give specific, actionable feedback rather than vague rejections.

## Safety Design

Safety is layered throughout the system, not bolted on at the end:

**Agent-level:** ResearcherAgent refuses to state uncertain things as fact. SummarizerAgent flags contradictions. CriticAgent includes safety as a scoring dimension.

**Pipeline-level:** SafetyAgent runs on every final output. Responses are BLOCKED if severity is HIGH or CRITICAL. Users are WARNED for MEDIUM severity.

**Constitutional-level:** SelfCritiqueEngine can run any response through a critique-revision loop against all principles. RevisionEngine rewrites problematic content.

**Logging-level:** Every safety check is logged regardless of outcome, creating a full audit trail.

## Prompt Engineering Decisions

Every agent prompt follows the same pattern: role definition, explicit rules, structured output format, and edge case handling. Key decisions:

**Why JSON output?** Forces the model to structure its thinking, makes parsing reliable, and enables downstream agents to extract specific fields without text parsing.

**Why confidence scores?** Makes uncertainty explicit. A 40% confidence plan automatically triggers fallback. A 30% research quality score tells the user to verify.

**Why constitutional principles as numbered lists?** The safety agent can reference specific principle IDs in violations, making it auditable and debuggable.

## Evaluation Results

Run `python -m evals.run_evals` to generate fresh results. The eval framework tests:

- **Accuracy (10 tests):** Factual questions with verifiable answers
- **Safety (8 tests):** Adversarial prompts that should be blocked
- **Consistency (3 tests):** Same prompt run multiple times
- **Edge Cases (5 tests):** Empty input, very long input, malformed input

Expected results on a clean run: 80%+ accuracy, 100% safety blocking of adversarial prompts, 90%+ consistency on factual questions.

## Limitations (Honest)

**No real web search:** ResearcherAgent uses Claude's training data only. For current events, a web search tool is needed.

**Latency:** 6 agents = 6+ API calls per request. Expect 15-45 seconds per workflow run.

**Cost:** Each workflow run uses approximately 3,000-10,000 tokens depending on task complexity.

**Constitutional AI is approximated:** The real Constitutional AI involves RLHF. This implementation uses the critique-revision loop but not the full training pipeline.

**Critic loop depth:** Max 2 revisions to control latency and cost. Some responses may still have issues after 2 loops.

## What I Would Build Next

1. **Real web search via MCP** - Connect ResearcherAgent to live web search tools
2. **Memory layer** - Persist context across sessions for better user experience
3. **Parallel agent execution** - Run independent steps concurrently to reduce latency
4. **Fine-tuned safety model** - Train a dedicated safety classifier instead of using Claude
5. **Human-in-the-loop** - Pause workflow for human review on low-confidence outputs

## Local Setup

```bash
# Clone and install
git clone https://github.com/Rajeshdevandla/agent-flow.git
cd agent-flow
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Run API server
uvicorn api.main:app --reload

# Or run Streamlit UI
streamlit run frontend/app.py

# Run evaluations
python -m evals.run_evals
```

## Project Structure

```
agentflow/
├── agents/
│   ├── base_agent.py          # Base class: Anthropic SDK, retry, logging
│   ├── planner_agent.py       # Task decomposition with confidence scoring
│   ├── researcher_agent.py    # Research with citations
│   ├── summarizer_agent.py    # Audience-aware summarization
│   ├── critic_agent.py        # NEW: Quality review with verdict
│   ├── safety_agent.py        # NEW: Constitutional AI safety layer
│   └── evaluator_agent.py     # NEW: Workflow scoring
├── orchestrator/
│   ├── workflow_engine.py     # 6-agent pipeline coordinator
│   ├── decision_logger.py     # NEW: Full audit trail
│   └── failure_recovery.py    # NEW: Graceful error handling
├── constitutional/
│   ├── principles.py          # NEW: 10-principle AI constitution
│   └── self_critique.py       # NEW: Constitutional AI loop
├── evals/
│   ├── run_evals.py           # NEW: 35+ test cases
│   └── scorer.py              # NEW: Multi-method scoring
├── frontend/
│   └── app.py                 # NEW: Streamlit UI
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Built With

- [Anthropic Claude](https://anthropic.com) - AI backbone
- [FastAPI](https://fastapi.tiangolo.com) - REST API
- [Streamlit](https://streamlit.io) - Frontend UI
- Constitutional AI inspired by [Bai et al., 2022](https://arxiv.org/abs/2212.08073)
