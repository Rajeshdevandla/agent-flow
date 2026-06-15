# AgentFlow v2.0 - Honest Limitations

This document explains what AgentFlow cannot do well, where it will fail, and what I would build next to fix these issues. Being honest about limitations is more useful than overselling capabilities.

## Current Limitations

### 1. No Real Memory Between Sessions

**What this means:** AgentFlow starts fresh every conversation. It has no memory of previous tasks, user preferences, or learned patterns. The memory/ directory contains stub files for future implementation.

**Why this is a problem:** A truly intelligent assistant should remember context. If you asked about machine learning yesterday and ask about neural networks today, the system treats these as completely unrelated requests.

**What I would build:** A vector database (like ChromaDB or Pinecone) for semantic search over past interactions. Short-term memory would persist within a session; long-term memory would survive restarts.

---

### 2. Cannot Access Real-Time Information

**What this means:** All agents rely solely on what Claude was trained on. There is no web search, no live data feeds, no API integrations.

**Why this is a problem:** ResearcherAgent claims to "research" topics but really just recalls training data. For current events, stock prices, recent papers, or live data, the system will either confabulate or correctly admit INSUFFICIENT_DATA.

**What I would build:** Integration with Anthropic's tool use feature to call search APIs (Brave, Tavily), access news feeds, and query databases in real time.

---

### 3. JSON Parsing Is Fragile

**What this means:** Every agent is expected to return structured JSON. Claude is very good at this, but not perfect. Under high token pressure or with unusual inputs, it sometimes returns malformed JSON or prose instead of JSON.

**Failure mode:** When JSON parsing fails, FailureRecovery triggers a retry. If all retries fail, the agent returns a fallback response. You lose the structured data.

**What I would build:** Use Anthropic's structured output features (when available) or implement a robust JSON extraction fallback that can parse JSON from mixed prose/code responses.

---

### 4. Safety Is Pattern-Matching, Not Airtight

**What this means:** SafetyAgent uses Claude to evaluate safety - which means it inherits Claude's own safety limitations. Adversarial prompts specifically designed to bypass Claude's safety training may succeed.

**What this is NOT:** A production-grade content moderation system. For high-stakes applications, you need dedicated safety infrastructure, human review pipelines, and continuous red-teaming.

**What I would build:** Additional rule-based safety filters that run before Claude (for obvious violations), integration with Anthropic's safety APIs if available, and human-in-the-loop review for flagged content.

---

### 5. Expensive to Run

**What this means:** A single workflow calls Claude 6 times (once per agent). Each call uses 500-2000 tokens. A complete workflow costs ~3,000-8,000 tokens, which adds up quickly.

**The math:** At current Claude pricing, 1,000 workflows/day would cost significant money. This is not a system you deploy for casual use without cost controls.

**What I would build:** Implement agent caching for repeated subtasks, a fast-path that skips expensive agents for simple queries, and cost tracking per workflow.

---

### 6. No Parallel Agent Execution

**What this means:** All 6 agents run sequentially. PlannerAgent must finish before ResearcherAgent starts. This is the biggest source of latency.

**Why sequential:** Some agents depend on previous agents' output (Researcher needs the Plan). But Critic and Evaluator could run simultaneously.

**What I would build:** Async execution using Python's asyncio, with a dependency graph that identifies which agents can run in parallel. Target: reduce end-to-end time by 40%.

---

### 7. Evaluation Framework Is Shallow

**What this means:** The eval suite has 26 test cases. That's not enough to be confident about system behavior. Professional AI systems have thousands of tests covering many more edge cases.

**What this is:** A demonstration framework that shows the right approach, not a production-grade eval system.

**What I would build:** At minimum 200+ accuracy tests covering different domains, 50+ safety tests including adversarial attacks, automated regression testing on every commit, and tracking of eval scores over time.

---

### 8. No Multi-User or Rate Limiting

**What this means:** The API has no authentication, no rate limiting, and no multi-tenant support. Anyone with the URL can send unlimited requests.

**Why this is a problem:** In production, this would immediately be abused.

**What I would build:** API key authentication, per-user rate limits, request queuing, and cost caps per API key.

---

## What Works Well

To be balanced, here's where the system actually performs:

- **Decision logging:** Every agent decision is captured. When something goes wrong, you can trace exactly which agent failed and why.
- **Safety layer:** The Constitutional AI-inspired safety check catches most obviously harmful requests. It correctly blocks jailbreak attempts in testing.
- **Structured outputs:** JSON-first design makes the system debuggable and chainable.
- **Failure recovery:** When an agent fails, the system degrades gracefully rather than crashing.
- **Audience adaptation:** SummarizerAgent genuinely produces different outputs for technical vs. non-technical users.

## The Honest Bottom Line

AgentFlow v2.0 is a well-architected demonstration system. It shows the right patterns for multi-agent AI: specialization, logging, safety, evaluation. For a personal project or portfolio piece, it's solid.

For production at scale, it needs: real memory, real-time data, airtight safety, cost controls, and a much larger eval suite. None of those are unsolvable - they're just engineering work.
