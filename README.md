# AgentFlow v2.0

> **Built for Anthropic** — A multi-agent AI orchestration system with Constitutional AI safety layers, full decision logging, and systematic evaluation framework — powered by Anthropic Claude SDK.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Anthropic Claude](https://img.shields.io/badge/powered%20by-Anthropic%20Claude-orange.svg)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-50%20passing-brightgreen.svg)](#)
[![Eval Score](https://img.shields.io/badge/eval%20score-78.6%25-yellow.svg)](docs/eval_report.md)

---

## Live Demo

>  **[Coming soon — deploying to Hugging Face Spaces / Streamlit Cloud]**
>
> To run locally, follow the [Quick Start](#quick-start) below.

---

## Recruiter Quick Summary

- **Constitutional AI safety layer** — 10 numbered principles with severity-based blocking (CRITICAL/HIGH/MEDIUM), runs on every single response before the user sees it; violations are traceable by principle ID in decision logs
- **Full decision audit trail** — every agent choice logged with reasoning, confidence score, and token count; nothing is a black box; when something goes wrong you can trace which agent made which decision
- **Systematic eval framework** — 55 test cases across accuracy, safety, consistency, and edge cases; honest C+ result (78.6%) with every failure documented in [docs/eval_report.md](docs/eval_report.md)

---

## Why I Built This

Most multi-agent systems fail in production for three reasons: they hallucinate confidently, they have no safety checks, and when something goes wrong you have no idea why. AgentFlow v2.0 addresses all three.

The original version used Amazon Bedrock and had three agents. This version switches entirely to the **Anthropic SDK directly** (no Bedrock), adds three new agents inspired by Anthropic's research, and implements a Constitutional AI safety layer based on Bai et al. (2022).

---

## System Architecture

```
╔══════════════════════════════════════════════════════════════════════╗
║                        AgentFlow v2.0                                ║
║                  Multi-Agent Orchestration System                    ║
╚══════════════════════════════════════════════════════════════════════╝

                    ┌─────────────────────┐
                    │    User / API Input  │
                    └──────────┬──────────┘
                               │ task prompt
                               ▼
                    ┌─────────────────────┐
                    │   ORCHESTRATOR      │
                    │  workflow.py        │◄── decision_logger.py
                    │  Routes between     │    (logs every step)
                    │  all 6 agents       │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  PLANNER AGENT  │  │RESEARCHER AGENT │  │SUMMARIZER AGENT │
│                 │  │                 │  │                 │
│ Decomposes task │  │ Gathers facts,  │  │ Synthesizes     │
│ into 7 steps    │  │ marks uncertain │  │ findings into   │
│ with confidence │  │ sources         │  │ 150-500 words   │
│ scoring         │  │ explicitly      │  │ with tone match │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                               │ output passed to
                               ▼
                    ┌─────────────────────┐
                    │   CRITIC AGENT      │
                    │                     │
                    │ Reviews summary for │
                    │ factual errors,     │
                    │ PASS / REVISE /     │
                    │ REJECT (max 2       │
                    │ revision cycles)    │
                    └──────────┬──────────┘
                               │ approved output
                               ▼
                    ┌─────────────────────┐
                    │   SAFETY AGENT      │◄── constitutional/
                    │                     │    principles.py
                    │ Checks 10 Const.    │
                    │ AI principles       │
                    │ BLOCK on CRITICAL   │
                    │ WARN on MEDIUM      │
                    │ Self-critique pass  │
                    └──────────┬──────────┘
                               │ safe output
                               ▼
                    ┌─────────────────────┐
                    │  EVALUATOR AGENT    │
                    │                     │
                    │ Scores final output │
                    │ across 5 dimensions │
                    │ Grade A-F assigned  │
                    │ Per-agent scores    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Final Response    │
                    │  + Decision Log     │
                    │  + Safety Report    │
                    │  + Eval Score       │
                    └─────────────────────┘

Data flow: Each agent receives structured JSON input and returns
structured JSON output. All intermediate outputs are logged.
Safety gate blocks workflow before output reaches the user.
```

---

## Sample Output

**Input task given to AgentFlow v2.0:**
> "Explain the potential risks of large language models being used in medical diagnosis."

---

**PlannerAgent output (truncated):**
```json
{
  "subtasks": [
    {
      "subtask_id": "PLAN_001",
      "description": "Research known LLM failure modes in medical contexts",
      "assigned_to": "ResearcherAgent",
      "estimated_complexity": "HIGH",
      "confidence": 0.82
    },
    {
      "subtask_id": "PLAN_002",
      "description": "Summarize risks into patient-facing and provider-facing categories",
      "assigned_to": "SummarizerAgent",
      "estimated_complexity": "MEDIUM"
    },
    {
      "subtask_id": "PLAN_003",
      "description": "Evaluate summary for medical accuracy and appropriate caveats",
      "assigned_to": "CriticAgent",
      "estimated_complexity": "HIGH"
    }
  ],
  "max_steps": 3,
  "confidence": 0.82
}
```

---

**ResearcherAgent output (excerpt):**
```json
{
  "findings": [
    {
      "claim": "LLMs produce confident-sounding incorrect diagnoses at measurable rates in benchmark studies",
      "confidence": 0.88,
      "source_type": "training_data",
      "caveats": "Benchmark studies may not reflect real clinical deployment conditions"
    },
    {
      "claim": "LLMs lack access to real-time patient history, imaging, and lab values",
      "confidence": 0.95,
      "source_type": "reasoning",
      "caveats": "Some multimodal systems partially address this"
    },
    {
      "claim": "Regulatory frameworks for AI medical devices (FDA 510k) are still evolving",
      "confidence": 0.71,
      "source_type": "uncertain",
      "caveats": "Regulations change frequently; verify current status"
    }
  ],
  "gaps": ["No access to post-2024 clinical trial data", "Cannot verify current FDA guidance"]
}
```

---

**SafetyAgent evaluation:**
```json
{
  "safety_evaluation": {
    "overall_status": "SAFE",
    "action": "CONTINUE",
    "principle_checks": [
      {
        "principle_id": 1,
        "status": "PASS",
        "severity": "LOW",
        "reasoning": "Educational content about medical risks does not cause harm"
      },
      {
        "principle_id": 9,
        "status": "WARN",
        "severity": "MEDIUM",
        "reasoning": "Summary should clearly state this is not medical advice to prevent misinformation"
      }
    ],
    "blocking_principles": [],
    "self_critique": "The content is educational and appropriately hedged. Risk of misuse as self-diagnosis justification is LOW given the framing, but a disclaimer should be added."
  }
}
```

---

**Final output score (EvaluatorAgent):**
```
Accuracy:           0.86
Completeness:       0.81
Safety Compliance:  0.94
Reasoning Quality:  0.83
User Value:         0.88
─────────────────────────
Overall Score:      0.86  →  Grade: B
```

> **Decision log:** 47 logged events across 6 agents | 3 revision cycles | 1 safety warning (MEDIUM) | Total: 4,218 tokens

---

## Evaluation Results (Actual — June 2026)

| Category | Tests Run | Passed | Score |
|---|---|---|---|
| Accuracy | 20 | 16 | 80.0% |
| Safety | 16 | 14 | 87.5% |
| Consistency | 10 | 8 | 80.0% |
| Edge Cases | 10 | 6 | 60.0% |
| **Overall** | **55** | **43** | **78.6%** |

**Grade: C+** — honest, not inflated.

Key findings:
- Safety agent correctly blocked all obvious harmful content (5/5 harmful content tests)
- Two safety gaps found: DAN jailbreaks assigned HIGH instead of CRITICAL severity; surveillance prompts not treated as CRITICAL
- Edge case handling is the weakest area (60%) — long inputs broke the 7-step plan limit; special characters caused JSON parse errors
- Uncertainty propagation from ResearcherAgent to SummarizerAgent breaks under certain conditions
- Full failure analysis: [docs/eval_report.md](docs/eval_report.md)

---

## Why This Matters for AI Safety

Three design decisions in this system are directly relevant to building safer AI:

**1. Constitutional AI safety layer.** Every response passes through a safety agent that evaluates it against 10 explicit principles before the user sees it. The principles are numbered (not prose) so that violations are traceable in logs — "blocked: principle 7" is auditable; "blocked: seemed risky" is not. The self-critique step catches indirect harms the explicit principles miss.

**2. Uncertainty that travels.** ResearcherAgent explicitly labels every claim as `training_data`, `reasoning`, or `uncertain`. SummarizerAgent is instructed to propagate those flags. This makes the system's confidence visible rather than hidden — a response that presents an uncertain claim as fact is a detectable failure mode, not a silent one.

**3. Full decision audit trail.** Every agent call, every intermediate output, every revision, every safety check is logged with timestamp, confidence score, token count, and reasoning. When something goes wrong, you can trace exactly which agent made which decision and why. Black-box AI systems make alignment work harder — this system makes its reasoning inspectable.

---

## Agents

| Agent | Role | Key Design Decision |
|---|---|---|
| PlannerAgent | Decomposes task into ≤7 subtasks | 7-step limit forces consolidation; confidence < 0.6 flags ambiguity |
| ResearcherAgent | Gathers and labels findings | Explicit `source_type` field prevents confident hallucination |
| SummarizerAgent | Synthesizes to 150-500 words | Weakest-link confidence scoring; uncertainty propagation enforced |
| CriticAgent | Reviews for factual errors | PASS/REVISE/REJECT with explicit thresholds; max 2 revision cycles |
| SafetyAgent | Constitutional AI check | 10 numbered principles; CRITICAL severity stops workflow immediately |
| EvaluatorAgent | Scores final output A-F | Weighted scoring: safety 25%, accuracy 30%, others 45% |

---

## Project Structure

```
agent-flow/
├── agents/                 # 6 agent implementations
│   ├── planner.py
│   ├── researcher.py
│   ├── summarizer.py
│   ├── critic.py
│   ├── safety_agent.py
│   └── evaluator.py
├── orchestrator/           # Workflow coordination
│   ├── workflow.py
│   └── decision_logger.py
├── constitutional/         # Safety principles
│   └── principles.py
├── evals/                  # Evaluation framework
│   ├── run_evals.py
│   └── test_cases/
│       ├── accuracy_tests.json     (20 tests)
│       ├── safety_tests.json       (16 tests)
│       ├── consistency_tests.json  (10 tests)
│       └── edge_cases.json         (10 tests)
├── docs/
│   ├── architecture.md
│   ├── prompt_engineering.md  ← prompt decisions + rationale
│   ├── eval_report.md         ← full evaluation report
│   └── limitations.md
├── tests/
│   ├── test_agents.py          (agent unit tests)
│   ├── test_orchestrator.py    (20 orchestrator tests)
│   └── test_safety.py          (30 safety/constitutional AI tests)
├── frontend/               # Streamlit UI
├── api/                    # FastAPI endpoints
├── memory/                 # Conversation memory
└── README.md
```

---

## Quick Start

```bash
git clone https://github.com/Rajeshdevandla/agent-flow.git
cd agent-flow
pip install -r requirements.txt

# Add your Anthropic API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Run the system
python -m orchestrator.workflow

# Run evaluations
python -m evals.run_evals

# Run tests (no API calls required — fully mocked)
pytest tests/ -v

# Launch Streamlit UI
streamlit run frontend/app.py
```

---

## What I Would Build Next

1. **Automated red-teaming** — use a separate Claude instance to generate adversarial inputs and stress-test the safety layer continuously, similar to Anthropic's Constitutional AI training pipeline
2. **Interpretability hooks** — expose attention patterns and intermediate reasoning steps to a monitoring dashboard, connecting to Anthropic's mechanistic interpretability research direction
3. **Evaluation benchmark** — expand the 55 test cases into a public benchmark for multi-agent safety, covering the specific failure modes (uncertainty propagation, revision loops, severity calibration) documented in this repo
4. **Multi-turn memory safety** — the current safety check runs per-response; a more robust system would check accumulated context across a conversation for gradual manipulation patterns

---

## Documentation

- [Prompt Engineering Decisions](docs/prompt_engineering.md) — why each agent prompt is written the way it is
- [Evaluation Report](docs/eval_report.md) — full results with every failure documented
- [Architecture Details](docs/architecture.md) — system design decisions
- [Known Limitations](docs/limitations.md) — honest assessment of what this system cannot do

---

## Model

All agents use `claude-opus-4-5` via the Anthropic Python SDK. No Amazon Bedrock. No middleware.

```python
import anthropic
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

---


## Related Projects

- [AskDocs AI](https://github.com/Rajeshdevandla/askdocs-ai) — PDF RAG chatbot using Amazon Bedrock and FAISS
- [AI Document Intelligence Platform](https://github.com/Rajeshdevandla/ai-document-intelligence-platform) — Enterprise document processing with Java microservices + OCR

---

*Built by Rajesh Devandla — June 2026*
