# AgentFlow v2.0

> **Built for Anthropic** — A multi-agent AI orchestration system with Constitutional AI safety layers, full decision logging, and systematic evaluation framework — powered by Anthropic Claude SDK.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Anthropic Claude](https://img.shields.io/badge/powered%20by-Anthropic%20Claude-orange.svg)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Recruiter Quick Summary

- **Constitutional AI safety layer** — 10 principles with severity-based blocking (CRITICAL/HIGH/MEDIUM), runs on every single response before the user sees it
- **Full decision audit trail** — every agent choice logged with reasoning, confidence score, and token count; nothing is a black box
- **Systematic eval framework** — 28 test cases across accuracy, safety, consistency, and edge cases with honest results (78.6% overall — not inflated)

---

## Why I Built This

Most multi-agent systems fail in production for three reasons: they hallucinate confidently, they have no safety checks, and when something goes wrong you have no idea why. AgentFlow v2.0 addresses all three.

The original version used Amazon Bedrock and had three agents. This version switches entirely to the **Anthropic SDK directly** (no Bedrock), adds three new agents inspired by Anthropic's research, and implements a Constitutional AI safety layer based on Bai et al. (2022).

The two things I care most about are: **you can always explain why the system did what it did**, and **the system never gives harmful output**. Every architectural decision flows from those two constraints.

---

## Architecture

```
USER INPUT
     |
     v
[PlannerAgent] ---------> Structured plan, confidence score (0-100), fallback if < 50
     |
     v
[ResearcherAgent] -------> Verified findings, citations, INSUFFICIENT_DATA if uncertain
     |
     v
[SummarizerAgent] -------> Audience-adapted response (technical/non-technical/researcher)
     |
     v
[CriticAgent] -----------> Quality gate: PASS / NEEDS_REVISION / FAIL
     |  ^                   loops back up to 2x on NEEDS_REVISION
     |  |___________________|
     v
[SafetyAgent] -----------> Constitutional check: PASS / WARN_USER / BLOCK
     |                      runs on EVERY response, no exceptions
     v
[EvaluatorAgent] --------> Scores workflow: task_completion, accuracy, clarity, safety
     |
     v
FINAL RESPONSE
+ Decision Log (every agent choice with reasoning)
+ Safety Report (which principles checked, any violations)
+ Quality Scores (A/B/C/D/F grade)
```

---

## The 6 Agents

### 1. PlannerAgent (Upgraded from v1)
Breaks down tasks into 3–7 ordered steps with dependency tracking. Returns confidence score 0–100. Falls back to a simpler plan if confidence < 50. Every planning decision is logged with reasoning.

**Design decision:** Confidence scoring was added because plans fail when the AI doesn't know what it doesn't know. A 30% confidence plan should trigger a fallback — without the score you're flying blind.

### 2. ResearcherAgent (Upgraded from v1)
Gathers information with explicit confidence levels (HIGH/MEDIUM/LOW) per finding. Returns `INSUFFICIENT_DATA` instead of hallucinating when facts are unavailable. Never presents uncertain information as fact.

**Design decision:** The hardest thing to get right in LLM systems is honest uncertainty. Most agents hallucinate confidently. This one is explicitly prompted to say "I don't know" and trained on the principle that a gap is better than a lie.

### 3. SummarizerAgent (Upgraded from v1)
Adapts output for three audience types: technical, non-technical, researcher. Stays under 300 words unless asked. Always ends with "Key uncertainty: [X]" — forces honest acknowledgment of what's still unknown.

### 4. CriticAgent (NEW)
Reviews every other agent's output before the user sees it. Checks five dimensions: accuracy, completeness, consistency, clarity, safety. Returns PASS/NEEDS_REVISION/FAIL with specific issues. Triggers a revision loop up to 2 times.

**Design decision:** Self-review before output caught approximately 30% of obvious errors in testing. The key insight from Anthropic's work is that models can critique better than they can generate on first pass.

### 5. SafetyAgent (NEW — most important)
Runs every response through 10 constitutional principles inspired by Bai et al. (2022). Actions: PASS / WARN_USER / BLOCK. CRITICAL violations always block. Every check is logged with which principle was triggered and why.

**The 10 principles:** (1) No physical harm instructions, (2) No privacy violations, (3) No deception/manipulation, (4) Respect user autonomy, (5) No illegal activity facilitation, (6) No hate/discrimination, (7) Honest about AI identity, (8) No jailbreak compliance, (9) Protect vulnerable users, (10) No misinformation.

### 6. EvaluatorAgent (NEW)
Scores the entire workflow after completion on five dimensions: task_completion, accuracy, clarity, conciseness, safety (0–100 each). Returns letter grade A–F. Tracks efficiency metrics: total time, total tokens, agent coordination quality.

---

## Constitutional AI Layer

Implemented in `constitutional/` based on Bai et al. (2022) *Constitutional AI: Harmlessness from AI Feedback*.

Three components:
- **`principles.py`** — 10-principle constitution with CRITICAL/HIGH/MEDIUM severity levels
- **`self_critique.py`** — Claude critiques its own output against principles (loop up to 3x)
- **`revision_engine.py`** — Rewrites outputs that fail critique while preserving factual accuracy

**Why this matters for AI safety:** Constitutional AI is Anthropic's approach to scalable oversight — instead of human review of every output, you define principles and let the model enforce them. This implementation shows I understand both the theory and the practical constraints of deploying it.

---

## Why This Matters for AI Safety

Three specific contributions to responsible AI deployment:

**1. The safety layer is non-optional and last.** SafetyAgent runs after CriticAgent — so it always sees the final output, not a draft. It cannot be bypassed by other agents. This is a deliberate architectural constraint, not a suggestion.

**2. Every decision is auditable.** DecisionLogger captures every agent call with timestamp, input, output, confidence, and token count. When something goes wrong (and it will), you can trace exactly which agent failed and why. Black-box AI systems that can't explain their decisions are dangerous at scale.

**3. Honest uncertainty is a first-class value.** ResearcherAgent returns INSUFFICIENT_DATA. SummarizerAgent ends every response with a key uncertainty. EvaluatorAgent scores and grades every run. The system is designed to surface what it doesn't know, not hide it.

---

## Evaluation Results (Actual Run — June 2026)

| Category | Tests Run | Passed | Failed | Score |
|---|---|---|---|---|
| Accuracy | 10 | 8 | 2 | 80.0% |
| Safety | 8 | 7 | 1 | 87.5% |
| Consistency | 5 | 4 | 1 | 80.0% |
| Edge Cases | 5 | 3 | 2 | 60.0% |
| **Overall** | **28** | **22** | **6** | **78.6%** |

**Overall Grade: C+ (78.6%)**

### Key Findings

**What worked well:**
- Safety blocking: 7/8 adversarial prompts correctly blocked (87.5%). The system refused jailbreak attempts, harmful content requests, and manipulation attempts reliably.
- Basic accuracy: 8/10 factual questions answered correctly. Failures were on ambiguous questions, not clear facts.
- Consistency: Claude gave consistent answers to the same prompt across 3 runs in 4/5 cases.

**What failed and why:**
- 1 safety test passed that should have been blocked: a subtle social engineering prompt that didn't trigger keyword-level detection. This is a known limitation of pattern-based safety — adversarial prompts designed to avoid obvious signals can slip through.
- 2 edge cases failed: empty input handling returned an error instead of a graceful "please provide a task" message, and very long inputs (1000+ chars) caused token pressure that degraded output quality.
- 1 consistency failure: a subjective question ("What is the best programming language?") gave different answers across runs — expected behavior, not a bug, but flagged as inconsistent.

**What surprised me:**
- The CriticAgent caught errors I didn't expect it to catch, including one case where ResearcherAgent stated something with HIGH confidence that was actually ambiguous. The self-review loop genuinely improved output quality.
- Edge case handling was the weakest area — 60% pass rate. Empty inputs and malformed requests expose gaps that normal testing misses. A production system needs explicit input validation before agents run.

See `docs/eval_report.md` for full failure analysis and methodology.

---

## Project Structure

```
agent-flow/
├── agents/
│   ├── base_agent.py          # Retry logic, logging, Anthropic SDK wrapper
│   ├── planner_agent.py       # Confidence scoring, fallback plans
│   ├── researcher_agent.py    # Citations, INSUFFICIENT_DATA flag
│   ├── summarizer_agent.py    # Audience adaptation (technical/non-tech/researcher)
│   ├── critic_agent.py        # Quality gate, PASS/NEEDS_REVISION/FAIL
│   ├── safety_agent.py        # Constitutional check, PASS/WARN/BLOCK
│   └── evaluator_agent.py     # Workflow scoring, A-F grade
├── orchestrator/
│   ├── workflow_engine.py     # 6-agent pipeline coordination
│   ├── decision_logger.py     # Logs every agent decision
│   └── failure_recovery.py   # Graceful degradation on agent failure
├── constitutional/
│   ├── principles.py          # 10-principle AI constitution
│   ├── self_critique.py       # Claude critiques its own output
│   └── revision_engine.py    # Rewrites outputs that fail critique
├── evals/
│   ├── test_cases/            # JSON test files (accuracy/safety/consistency/edge)
│   ├── run_evals.py           # Evaluation runner
│   └── scorer.py             # Multi-method scoring
├── frontend/
│   └── app.py                # Streamlit UI with live agent status
├── api/
│   └── main.py               # FastAPI REST server
├── docs/
│   ├── architecture.md        # System design decisions
│   ├── prompt_engineering.md  # Every prompt decision explained
│   ├── eval_report.md         # Full evaluation findings
│   └── limitations.md        # Honest limitations
├── tests/
│   ├── test_agents.py
│   ├── test_orchestrator.py
│   └── test_safety.py
├── config/
│   └── anthropic_config.py   # Centralized SDK configuration
├── memory/
│   ├── short_term.py          # Session memory (stub)
│   └── long_term.py          # Persistent memory (stub — see limitations)
├── .env.example
├── requirements.txt
└── Dockerfile
```

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/Rajeshdevandla/agent-flow.git
cd agent-flow

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 5. Run the API
uvicorn api.main:app --reload

# 6. Run the frontend (separate terminal)
streamlit run frontend/app.py

# 7. Run evaluations
python -m evals.run_evals
```

---

## Prompt Engineering Decisions

Full analysis in `docs/prompt_engineering.md`. Key decisions:

**Why JSON output from every agent:** JSON forces structure. Free-form text is unchainable between agents. When an agent returns `{"confidence": 87, "plan": [...]}` you can validate it, route on it, and pass specific fields downstream. Prose output breaks the pipeline.

**Why confidence scores:** Confidence lets the orchestrator make decisions. A plan with 30% confidence triggers a fallback. Research with LOW confidence gets flagged for the user. Without scores, you can't programmatically distinguish "I'm sure" from "I'm guessing."

**Why Constitutional AI prompting works:** Numbered principles outperform prose rules because they create clear reference points for self-critique. "You violated principle 3" is actionable. "Be more ethical" is not.

---

## Honest Limitations

Full analysis in `docs/limitations.md`. Short version:

- **No real memory between sessions** — agents start fresh every time
- **No real-time data** — ResearcherAgent uses training knowledge, not live search
- **JSON parsing is fragile** — under token pressure, Claude occasionally returns prose instead of JSON
- **Safety is not airtight** — adversarial prompts designed to avoid obvious signals can bypass detection
- **Expensive to run** — 6 API calls per workflow; not free at scale
- **No parallel execution** — agents run sequentially; target improvement is asyncio for 40% speedup

---

## What I Would Build Next

1. **Real-time web search** — integrate Anthropic tool use with Brave/Tavily API so ResearcherAgent accesses live data, not just training knowledge
2. **Vector memory** — ChromaDB or Pinecone for semantic retrieval across sessions, enabling agents to learn from past runs
3. **Async agent execution** — run Critic and Evaluator in parallel using asyncio; target 40% latency reduction
4. **Larger eval suite** — 200+ accuracy tests, 50+ adversarial safety tests, automated regression on every commit
5. **Human-in-the-loop for WARN cases** — SafetyAgent WARN_USER currently just flags; a production system needs a review queue with human escalation

These connect directly to Anthropic's research priorities: scalable oversight, interpretability, and safe deployment of capable systems.

---

## References

- Bai, Y. et al. (2022). *Constitutional AI: Harmlessness from AI Feedback*. Anthropic. https://arxiv.org/abs/2212.08073
- Anthropic Claude SDK: https://docs.anthropic.com/
- Model used: `claude-opus-4-5`
