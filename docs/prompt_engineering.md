# Prompt Engineering Decisions — AgentFlow v2.0

> **Document purpose:** This is an engineering record of every significant prompt decision made during AgentFlow v2.0 development. It explains *what* the prompts look like, *why* they were written that way, and what failed before arriving at the current approach. Written for technical reviewers who want to understand the reasoning, not just the output.

---

## Overview

Multi-agent systems fail in ways that single-agent systems don't. When six agents pass information sequentially, prompt errors compound — a vague instruction to PlannerAgent becomes an ambiguous task decomposition, which becomes an unfocused research query, which becomes a weak summary, which fails the critic review. The failure is hard to debug because it happened three steps earlier.

This document covers the prompt engineering decisions that addressed this compounding problem. The core insight: **each agent needs a prompt that does three things simultaneously** — define scope (what it should do), define format (how it should output), and define failure modes (what it should do when uncertain or out-of-scope).

Model used throughout: `claude-opus-4-5` via Anthropic SDK (not Amazon Bedrock).

---

## Agent-by-Agent Prompt Analysis

### PlannerAgent

**The Prompt (current version):**
```
You are PlannerAgent, responsible for decomposing complex user tasks into structured, executable subtasks for a multi-agent system.

Given a user task, produce a JSON plan with the following structure:
{
  "task_id": "unique identifier",
  "original_task": "verbatim user input",
  "subtasks": [
    {
      "subtask_id": "PLAN_001",
      "description": "specific, actionable description",
      "assigned_to": "ResearcherAgent | SummarizerAgent | CriticAgent",
      "dependencies": [],
      "estimated_complexity": "LOW | MEDIUM | HIGH",
      "success_criteria": "measurable outcome"
    }
  ],
  "max_steps": 7,
  "confidence": 0.0-1.0,
  "reasoning": "why you decomposed it this way"
}

Rules:
- Maximum 7 subtasks. If a task requires more, consolidate.
- Assign each subtask to exactly one agent.
- Confidence below 0.6 means the task is ambiguous — flag it.
- Never generate subtasks you cannot assign to an existing agent.
```

**Why This Wording:**

*Role definition:* "responsible for decomposing" is more precise than "you help decompose." The word "responsible" creates ownership — the agent treats the decomposition as its primary output, not a stepping stone.

*JSON output format:* Originally used prose output ("First do X, then do Y"). This broke downstream parsing immediately. Switched to strict JSON after the first integration test. The schema is deliberately verbose — `success_criteria` forces the planner to think about what "done" means, which surfaces ambiguous tasks early.

*7-step maximum:* Without this constraint, Claude would generate 12-15 subtasks for moderately complex queries. Most were redundant. The 7-step limit forces consolidation and produces cleaner handoffs to downstream agents.

*Confidence scoring:* Added after noticing Claude would confidently plan tasks it clearly didn't have enough information to decompose. The 0.6 threshold was chosen empirically — below it, the plan usually had missing dependencies or wrong agent assignments.

**What I Tried First:**
- Plain English output: "Break this task into steps." → Unparseable downstream, different format every time.
- No agent assignment: Just listed steps without specifying who does them → Orchestrator had to guess; caused wrong agent calls.
- Unlimited steps: Plans with 15+ steps → most were micro-tasks that added latency without improving output.

---

### ResearcherAgent

**The Prompt (current version):**
```
You are ResearcherAgent, responsible for gathering and synthesizing information to answer a specific subtask.

You receive a subtask description and must return a JSON research report:
{
  "subtask_id": "matches incoming subtask",
  "findings": [
    {
      "claim": "specific factual statement",
      "confidence": 0.0-1.0,
      "source_type": "training_data | reasoning | uncertain",
      "caveats": "what might be wrong or outdated about this"
    }
  ],
  "synthesis": "2-3 paragraph summary connecting all findings",
  "gaps": ["things you could not find or verify"],
  "recommended_next_step": "what SummarizerAgent should emphasize"
}

Rules:
- Distinguish between what you know from training data vs. what you are inferring.
- Mark anything time-sensitive (statistics, current events) as 'uncertain'.
- List gaps honestly — incomplete research is better than fabricated research.
- Do not answer beyond the subtask scope.
```

**Why This Wording:**

*source_type field:* This was the most important addition to ResearcherAgent. Claude has a tendency to state inferences with the same confidence as facts. Forcing explicit labeling of `training_data | reasoning | uncertain` makes hallucination visible rather than hidden.

*caveats field:* Directly addresses the overconfidence problem. When Claude must write a caveat for each claim, it thinks about what could be wrong. Claims without meaningful caveats tend to be more robust.

*gaps field:* "Incomplete research is better than fabricated research" is a direct instruction against confabulation. Without this, the agent fills gaps with plausible-sounding but unreliable information.

*scope constraint:* "Do not answer beyond the subtask scope" prevents research drift — Claude exploring tangential interesting topics instead of answering the specific question.

**What I Tried First:**
- No source typing: Just "research this topic" → couldn't distinguish confident facts from guesses in downstream processing.
- Combined research + summarization in one prompt: Saved one agent call but produced worse output on both dimensions — the agent was doing two things mediocrely.

---

### SummarizerAgent

**The Prompt (current version):**
```
You are SummarizerAgent, responsible for synthesizing research findings into a coherent, audience-appropriate response.

You receive research reports and must return:
{
  "summary": "main response, 200-400 words",
  "key_points": ["3-5 bullet points, each a complete sentence"],
  "confidence": 0.0-1.0,
  "tone": "professional | educational | conversational",
  "flagged_uncertainties": ["claims from research marked as uncertain that appear in summary"],
  "word_count": integer
}

Rules:
- Maintain the uncertainty flags from ResearcherAgent — do not present uncertain claims as facts.
- Word count must be between 150 and 500. Flag if task requires more; do not silently exceed.
- Confidence should reflect the weakest link in the research chain, not the average.
- Match tone to the original user task context.
```

**Why This Wording:**

*Uncertainty propagation:* The critical constraint is "do not present uncertain claims as facts." Without this, summaries sound more confident than the underlying research. The `flagged_uncertainties` field forces the agent to explicitly carry uncertainty forward — a downstream CriticAgent can then check whether the summary appropriately hedged those claims.

*Word count bounds:* 150-500 words with a hard flag prevents two failure modes: summaries so short they miss important nuance, and summaries so long they defeat the purpose of summarization. The "flag, don't silently exceed" rule creates an observable output rather than silent non-compliance.

*Weakest-link confidence:* Averaging confidence across findings produces artificially high scores. If three claims are high-confidence and one is uncertain, the summary is only as trustworthy as that uncertain claim. Weakest-link scoring is more honest.

---

### CriticAgent

**The Prompt (current version):**
```
You are CriticAgent, responsible for evaluating the quality and accuracy of summaries produced by SummarizerAgent.

You receive a summary and the original research report. Return:
{
  "verdict": "PASS | REVISE | REJECT",
  "score": 0.0-1.0,
  "issues": [
    {
      "type": "factual_error | missing_caveat | scope_drift | logical_inconsistency | tone_mismatch",
      "description": "specific description of the issue",
      "severity": "LOW | MEDIUM | HIGH",
      "location": "quote the specific text with the issue"
    }
  ],
  "revision_instructions": "specific instructions for SummarizerAgent if verdict is REVISE",
  "passes_safety_gate": true | false
}

Rules:
- REJECT only if there is a factual error rated HIGH severity.
- REVISE if there are 2+ MEDIUM issues or any missing caveat from the research.
- PASS only if score >= 0.75 and no HIGH severity issues.
- Maximum 2 revision cycles — after 2, pass to safety gate regardless.
- Be specific in revision_instructions — vague feedback causes loops.
```

**Why This Wording:**

*Explicit verdict thresholds:* PASS/REVISE/REJECT without thresholds produces inconsistent verdicts. Claude's internal calibration for "good enough" varies. Explicit rules (score >= 0.75, no HIGH issues) make the gate deterministic and auditable.

*Revision loop limit:* Without "maximum 2 revision cycles," the critic and summarizer would occasionally enter feedback loops. The summarizer would make a change, the critic would find a new issue with the change, and so on. Capping at 2 forces a decision.

*"Be specific in revision_instructions"*: Discovered through iteration that vague feedback like "improve clarity" caused the summarizer to change something arbitrary, not the actual problem. Specificity requirement improved revision quality significantly.

---

### SafetyAgent

**The Prompt (current version — most important section):**
```
You are SafetyAgent, implementing Constitutional AI safety review for AgentFlow v2.0.

You receive any agent output and must evaluate it against 10 constitutional principles:

PRINCIPLES:
1. Do not produce content that could cause physical harm
2. Do not assist with illegal activities or circumventing laws
3. Do not generate personally identifiable information without consent
4. Do not produce discriminatory content targeting protected groups
5. Do not facilitate manipulation or deception of individuals
6. Do not produce content that exploits or endangers minors
7. Do not assist with unauthorized access to systems or data
8. Do not produce content that violates intellectual property
9. Do not generate content designed to spread misinformation
10. Do not facilitate coordinated harassment campaigns

For each principle, return:
{
  "safety_evaluation": {
    "principle_checks": [
      {
        "principle_id": 1-10,
        "status": "PASS | WARN | BLOCK",
        "severity": "LOW | MEDIUM | HIGH | CRITICAL",
        "reasoning": "why this status was assigned",
        "relevant_content": "quote the specific content flagged, if any"
      }
    ],
    "overall_status": "SAFE | REVIEW | BLOCKED",
    "action": "CONTINUE | FLAG_FOR_REVIEW | STOP_WORKFLOW",
    "blocking_principles": [list of principle IDs that triggered BLOCK],
    "self_critique": "what additional risks might exist that weren't explicitly covered"
  }
}

Rules:
- BLOCK on any CRITICAL severity finding — stop immediately.
- BLOCK on 2+ HIGH severity findings in combination.
- WARN on MEDIUM severity — flag but do not stop workflow.
- PASS on LOW severity — log but continue.
- The self_critique field must always be completed — if you find nothing, explain why.
- Err on the side of WARN over PASS when uncertain.
```

**Why This Wording:**

*Numbered principles:* After testing prose rules ("be helpful, be harmless, be honest"), numbered principles performed significantly better. Claude can reference specific principles by number, making reasoning traceable. "This violates principle 7" is more precise than "this seems risky."

*Severity-based action mapping:* The BLOCK/WARN/PASS system with explicit severity thresholds prevents both over-blocking (flagging harmless content as dangerous) and under-blocking (letting harmful content through as low-priority). The 2+ HIGH rule handles edge cases where multiple medium-serious issues combine into a serious overall risk.

*self_critique field:* Directly inspired by Constitutional AI — Claude reviews its own safety evaluation. This catches cases where Claude misses an indirect harm that isn't explicitly covered by the 10 principles. In testing, the self-critique field surfaced 3 risks that the principle-by-principle check missed.

*"Err on the side of WARN over PASS"*: Safety errors are asymmetric — a false negative (missing a real risk) is much worse than a false positive (flagging something safe). This instruction shifts the decision boundary appropriately.

**What I Tried First:**
- Single binary SAFE/UNSAFE output: Lost all nuance — borderline content either always passed or always blocked with no middle ground.
- Prose safety rules: Inconsistent application; Claude interpreted the same rule differently in different contexts.
- No self-critique: Missed indirect harms consistently in adversarial test cases.

---

### EvaluatorAgent

**The Prompt (current version):**
```
You are EvaluatorAgent, responsible for scoring the final output of AgentFlow v2.0 across quality dimensions.

You receive the complete workflow output (plan, research, summary, critic review, safety evaluation) and return:
{
  "evaluation": {
    "scores": {
      "accuracy": 0.0-1.0,
      "completeness": 0.0-1.0,
      "safety_compliance": 0.0-1.0,
      "reasoning_quality": 0.0-1.0,
      "user_value": 0.0-1.0
    },
    "overall_score": 0.0-1.0,
    "grade": "A | B | C | D | F",
    "per_agent_performance": {
      "PlannerAgent": {"score": 0.0-1.0, "notes": "specific observation"},
      "ResearcherAgent": {"score": 0.0-1.0, "notes": "specific observation"},
      "SummarizerAgent": {"score": 0.0-1.0, "notes": "specific observation"},
      "CriticAgent": {"score": 0.0-1.0, "notes": "specific observation"},
      "SafetyAgent": {"score": 0.0-1.0, "notes": "specific observation"}
    },
    "failure_points": ["list of specific things that went wrong in this workflow run"],
    "improvement_suggestions": ["concrete suggestions for this specific run"]
  }
}

Rules:
- Overall score is weighted: accuracy (30%) + completeness (20%) + safety_compliance (25%) + reasoning_quality (15%) + user_value (10%).
- Grade thresholds: A >= 0.9, B >= 0.8, C >= 0.7, D >= 0.6, F < 0.6.
- Per-agent scores must be justified — no score without a note.
- failure_points must be specific ("SummarizerAgent exceeded word count limit") not generic ("output was poor").
```

**Why This Wording:**

*Weighted scoring:* Unweighted averaging treats all dimensions equally. Safety compliance and accuracy matter more than user-friendliness of tone for an AI safety-focused system, so the weights reflect that priority explicitly.

*Per-agent scoring:* Aggregate scores hide which agent caused a problem. Per-agent scoring makes debugging faster — when a run scores poorly, you can identify whether it was a planning failure, a research failure, or a summarization failure without reading all the intermediate outputs.

*specific failure_points:* "Output was poor" is useless for debugging. "SummarizerAgent exceeded word count limit and CriticAgent didn't flag it" is actionable. The specificity requirement prevents surface-level evaluation.

---

## Constitutional AI Prompting

### How Claude Critiques Its Own Outputs

The SafetyAgent implements a simplified version of Constitutional AI: Claude evaluates its own outputs against explicit principles rather than relying on implicit values. The self_critique field goes a step further — Claude looks for risks that aren't covered by the enumerated principles.

This works better than fine-tuning for a few reasons: it's interpretable (you can see the reasoning), it's adjustable (adding a principle is a one-line change), and it surfaces uncertainty (Claude can say "I'm not sure if this violates principle 6" rather than making a silent decision).

### Why Numbered Principles Work Better Than Prose Rules

In testing, prose rules like "avoid harmful content" produced inconsistent results. Claude's interpretation of "harmful" varied by context. Numbered principles with explicit scope force Claude to consider each type of risk separately, making it harder to implicitly justify skipping a check.

Numbered principles also make reasoning auditable: "BLOCK — principle 7 violated" is traceable in logs. "BLOCK — harmful content detected" is not.

### How Severity Levels Affect Prompting Strategy

The severity model (CRITICAL → HIGH → MEDIUM → LOW) was necessary because the binary SAFE/UNSAFE model produced too many false positives. The key insight: blocking should be proportional to severity, and severity should be proportional to potential real-world harm.

CRITICAL severity triggers immediate workflow stop. This is reserved for content that could facilitate serious harm (illegal instructions, exploitation of minors, etc.). HIGH severity triggers blocking if two or more are present together — acknowledging that combined moderate risks can exceed the threshold. MEDIUM severity triggers a WARN flag visible in decision logs without stopping the workflow.

---

## Key Lessons Learned

**1. Claude needs format constraints more than content instructions.**
Instructions like "be thorough" or "be accurate" produce inconsistent results. Format constraints (JSON schema, word limits, required fields) produce consistent results. The format IS the instruction.

**2. Uncertainty must be made visible to propagate correctly.**
If ResearcherAgent marks something as uncertain internally but outputs a clean synthesis, SummarizerAgent has no way to preserve that uncertainty. Explicit uncertainty fields (`source_type`, `caveats`, `flagged_uncertainties`) force uncertainty to travel through the pipeline.

**3. Role definitions change behavior more than task descriptions.**
"You are ResearcherAgent, responsible for X" behaves differently than "Research X." Role definitions activate more consistent behavioral patterns in Claude — the agent maintains its role constraints across a longer context window.

**4. Confidence scoring is calibrated differently than I expected.**
Claude initially assigned confidence scores in a narrow band (0.65-0.85) regardless of actual certainty. Calibration required explicit instruction about what low/high confidence should mean and examples of when to use each end of the scale.

**5. Revision loops need explicit termination conditions.**
Without "maximum 2 revision cycles," critic-summarizer loops occasionally became infinite. The fix is simple but non-obvious: revision must have a stated exit condition, not just a quality threshold. Quality thresholds alone don't guarantee termination if the summarizer keeps introducing new issues.

---

## What I Would Do Differently

**Fewer agents, clearer scope.** Six agents felt like the right number during design. In practice, PlannerAgent and EvaluatorAgent overlap in some dimensions — both assess task quality. I'd redesign with four agents: Planner, Researcher, Summarizer+Critic (merged), and Safety. The merge would reduce latency and eliminate the handoff complexity between two agents doing related work.

**Test prompts before building the orchestration layer.** I built orchestration first, then discovered prompt failures during integration testing. The correct order is: test each agent prompt in isolation against 10 representative inputs, verify the output schema is consistent, then build the orchestration layer on top. This would have surfaced the JSON format issues and confidence calibration problems much earlier.

**Add a meta-prompt for the orchestrator.** The orchestrator currently uses hardcoded logic to route between agents. A better design would give the orchestrator its own prompt for handling unexpected failure modes — a kind of "recovery strategy" prompt that kicks in when an agent returns an unexpected output. Currently, unexpected outputs crash the pipeline silently.

**Track prompt versions explicitly.** As prompts evolved, I updated them in place without version tracking. By the end, I couldn't reconstruct which prompt change caused which improvement. Prompt versioning (even just a comment with date and rationale) would make iteration more systematic.

---

*Last updated: June 2026 | Model: claude-opus-4-5 | Author: Rajesh Devandla*
