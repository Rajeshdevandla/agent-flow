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
- WorkflowEngine returns WARN_USER details in its `warnings` string alongside
  the candidate response. Empty or whitespace-only issues produce a general
  caution message; PASS returns an empty warning string. The API continues to
  expose the structured review in `safety_report`.
- Requires a known action, a finite numeric score from 0-100, and string lists
  for issues and violations. Invalid reviews block the candidate response.
- The production engine also blocks when the safety agent raises an exception;
  evaluation is skipped and unchecked content is withheld.
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
- Each sequential run gets a new workflow ID, audit logger, recovery history,
  and agent usage counters while preserving configured agents and model clients.
  Returned reports remain independent snapshots. Use separate engine instances
  for concurrent requests.

**DecisionLogger** (`decision_logger.py`)
- Logs every agent decision with timestamp and metadata
- Per-workflow, in-memory audit records with JSON-serializable session reports
- API workflow responses use the logger's UUID-based `wf_` identifier, so
  requests started within the same second have distinct audit identities.
  Treat workflow IDs as opaque strings, not timestamps.
- Reports must be explicitly exported by the caller to survive process restarts;
  prompts and outputs are not automatically written to disk
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

The workflow API rejects empty or whitespace-only tasks with HTTP 422 before
creating a model client or running agents. Valid task text is preserved exactly,
including indentation, newlines, and surrounding whitespace.

Unexpected exceptions during API pipeline execution return a generic HTTP 500
message. The API logs only the workflow ID and exception class, without the
exception message or traceback. Deliberate HTTP errors, including safety
blocks, retain their existing status and response.

See `docs/limitations.md` for honest discussion of system limitations.

## Performance Characteristics

CI builds the `api` Docker target and runs its actual entrypoint and health check
inside the required `test` job. The smoke container has no external network and
an empty `ANTHROPIC_API_KEY`. It must become Docker-healthy within 120 seconds,
serve repeated root requests, and report degraded provider diagnostics. Failure
prints container logs/state; cleanup removes only the temporary smoke container.
To reproduce locally with Docker installed:

```bash
docker build --target api --tag agentflow-api:smoke .
bash scripts/smoke_api_container.sh agentflow-api:smoke
```

This checks image startup and local API behavior, not hosted deployment health
or successful model inference.

- The API Docker health probe uses `GET /` for process liveness without creating
  an Anthropic client or making model calls. A healthy container does not imply
  that the provider is configured or available. `GET /health` remains an explicit
  provider diagnostic: it makes a model request when credentials are configured
  and can incur usage. It reports `healthy` or `degraded` in the response body,
  with HTTP 200 in either case; do not use its HTTP status as a readiness signal.
- Workflow and provider health-check routes run in FastAPI's worker thread pool
  because the Anthropic client and agent pipeline are synchronous. A waiting
  model call does not block the event loop from serving lightweight routes such
  as `/`. Agents within each workflow still run sequentially. Worker capacity is
  bounded; this is not a job queue or unlimited concurrency, and cancelling an
  HTTP request does not guarantee cancellation of an in-flight model call.
- API agent `duration` and workflow `total_duration` are elapsed seconds
  measured with a monotonic performance counter. Agent durations cover the
  complete `run` call, including retries and backoff; the workflow total also
  includes orchestration overhead after client initialization. Skipped agents
  have no result entry. Wall-clock changes do not affect these measurements.
- API `tokens_used` reports each executed agent's recorded input plus output
  tokens. `total_tokens` sums those agents, including the evaluator when enabled.
  Skipped agents contribute nothing and counters are fresh for each request.
  Failed attempts without usage metadata add no tokens; these counts are
  observed model usage, not a billing estimate.
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
