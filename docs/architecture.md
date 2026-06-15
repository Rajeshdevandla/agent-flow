# AgentFlow v2.0 Architecture

## System Overview

AgentFlow v2.0 is a multi-agent AI orchestration system built on Anthropic's Claude. The system chains six specialized agents in a pipeline, with each agent performing a distinct role before passing output to the next.

## Architecture Diagram

```
USER INPUT
    |
    v
[PlannerAgent] -----> Structured plan with confidence score
    |
    v
[ResearcherAgent] --> Verified findings with citations
    |
    v
[SummarizerAgent] --> Audience-adapted summary
    |
    v
[CriticAgent] -------> Quality review (PASS/NEEDS_REVISION/FAIL)
    |                   (loops back if NEEDS_REVISION, max 2x)
    v
[SafetyAgent] -------> Safety check (PASS/WARN_USER/BLOCK)
    |
    v
[EvaluatorAgent] ----> Quality scores + grade
    |
    v
FINAL RESPONSE + Decision Log + Safety Report
```

## Component Architecture

### Agents Layer (`agents/`)

Each agent follows the same base pattern:
1. Receive structured input
2. Call Claude with specialized system prompt
3. Parse and validate JSON response
4. Log decision to DecisionLogger
5. Return structured output

**BaseAgent** (`base_agent.py`)
- Abstract base class for all agents
- Handles retry logic (3 attempts with exponential backoff)
- Manages Anthropic SDK client
- Provides `call_claude()` helper
- Logs every call for audit trail

**PlannerAgent** (`planner_agent.py`)
- Creates execution plan with 3-7 steps
- Returns confidence score (0-100)
- Triggers fallback plan if confidence < 50
- Design decision: Confidence scoring added because plans fail when the AI doesn't know what it doesn't know

**ResearcherAgent** (`researcher_agent.py`)
- Gathers and validates information
- Returns INSUFFICIENT_DATA when facts unavailable
- Marks each finding with confidence level (HIGH/MEDIUM/LOW)
- Design decision: Never fabricate facts - return honest uncertainty instead

**SummarizerAgent** (`summarizer_agent.py`)
- Adapts output for three audience types: technical, non-technical, researcher
- Stays under 300 words unless asked
- Always ends with "Key uncertainty: [X]"
- Design decision: Audience adaptation is critical - same facts need different framing

**CriticAgent** (`critic_agent.py`)
- Reviews output across 5 dimensions: accuracy, completeness, consistency, clarity, safety
- Returns PASS/NEEDS_REVISION/FAIL verdict
- Triggers revision loop (max 2 iterations) on NEEDS_REVISION
- Design decision: Self-review catches ~30% of errors before user sees them

**SafetyAgent** (`safety_agent.py`)
- Constitutional AI-inspired safety layer
- Evaluates 10 principles (5 CRITICAL, 3 HIGH, 2 MEDIUM)
- Three possible actions: PASS, WARN_USER, BLOCK
- Runs on EVERY response, no exceptions
- Design decision: Safety must be non-optional and always last before user

**EvaluatorAgent** (`evaluator_agent.py`)
- Scores completed workflow on 5 dimensions
- Provides letter grade (A-F)
- Tracks efficiency metrics (time, tokens, coordination)
- Design decision: Evaluation data helps identify systematic weaknesses over time

### Orchestrator Layer (`orchestrator/`)

**WorkflowEngine** (`workflow_engine.py`)
- Coordinates the 6-agent pipeline
- Handles agent-to-agent data passing
- Manages critic revision loop
- Routes to FailureRecovery on agent failure

**DecisionLogger** (`decision_logger.py`)
- Logs every agent decision with timestamp and metadata
- Persistent JSON log for audit trails
- Query API for filtering logs
- Design decision: Full decision logging is essential for debugging multi-agent systems

**FailureRecovery** (`failure_recovery.py`)
- Handles three failure types: timeout, API error, invalid JSON
- Exponential backoff retry strategy
- Graceful degradation when agents fail
- Design decision: Agents will fail in production; recovery strategy prevents total system failure

### Constitutional AI Layer (`constitutional/`)

**Principles** (`principles.py`)
- Defines 10-principle AI constitution
- Principles have severity levels: CRITICAL, HIGH, MEDIUM
- CRITICAL violations always BLOCK
- Based on Bai et al. (2022) Constitutional AI paper

**SelfCritique** (`self_critique.py`)
- Claude critiques its own output against principles
- Revision loop runs up to 3 iterations
- Stops early if principles satisfied
- Design decision: Self-critique catches subtle violations the safety checker might miss

**RevisionEngine** (`revision_engine.py`)
- Rewrites outputs that fail critique
- Maintains factual accuracy during revision
- Tracks revision history

### Evaluation Layer (`evals/`)

Four test categories:
1. **Accuracy tests** (10): Verifies factual correctness
2. **Safety tests** (8): Adversarial prompts that should be BLOCKED
3. **Consistency tests** (5 runs): Same prompt should give consistent answers
4. **Edge cases** (5): Empty input, very long input, non-English, malformed

## Data Flow

All inter-agent communication uses structured JSON:

```json
{
  "agent": "PlannerAgent",
  "timestamp": "2024-01-15T10:30:00",
  "input": {"task": "..."},
  "output": {
    "plan": [...],
    "confidence": 87,
    "reasoning": "..."
  },
  "tokens_used": 450,
  "duration_ms": 1200
}
```

## Design Decisions

### Why JSON everywhere?
JSON output forces the model to be structured and parseable. Free-form text is hard to chain between agents. When a model returns JSON, you can validate it, extract specific fields, and pass structured data downstream.

### Why confidence scores?
Confidence scores let the orchestrator make decisions. A plan with 30% confidence should trigger a fallback. A research result with LOW confidence should be flagged. Without scores, you're flying blind.

### Why separate agents instead of one big prompt?
Specialization improves quality. A prompt focused only on safety catches more violations than a general-purpose prompt. Separation also makes debugging easier - when something fails, you know which agent failed.

### Why Constitutional AI?
Constitutional AI (Bai et al., 2022) is Anthropic's approach to scalable oversight. Instead of human review of every output, you define principles and let the model critique itself. This gives you systematic safety coverage at scale.

### Why is SafetyAgent last before user?
Safety must be the final gate. Critic can improve quality, but safety is non-negotiable. Placing safety last ensures it sees the final output, not an intermediate draft.

## Known Limitations

See `docs/limitations.md` for honest discussion of system limitations.

## Performance Characteristics

- Typical workflow: 6-12 seconds end-to-end
- Token usage: ~3,000-8,000 tokens per complete workflow
- Agent timeout: 60 seconds per agent
- Retry budget: 3 attempts per agent

## Dependencies

See `requirements.txt` for full dependency list. Key dependencies:
- `anthropic>=0.40.0` - Claude API
- `fastapi>=0.115.0` - REST API server
- `streamlit>=1.40.0` - Frontend UI
- `pydantic>=2.10.0` - Data validation
