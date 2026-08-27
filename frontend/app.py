"""Public, zero-cost Streamlit demo for AgentFlow v2.0.

This interface demonstrates the six-agent workflow with curated, deterministic
examples. It never calls an external model and therefore needs no API key.
"""

import time
from typing import Any

import streamlit as st

st.set_page_config(
    page_title="AgentFlow v2.0 Demo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

AGENTS = [
    "PlannerAgent",
    "ResearcherAgent",
    "SummarizerAgent",
    "CriticAgent",
    "SafetyAgent",
    "EvaluatorAgent",
]

SCENARIOS: dict[str, dict[str, Any]] = {
    "LLM risks in medical diagnosis": {
        "task": "Explain the potential risks of large language models being used in medical diagnosis.",
        "audience": "Non-technical",
        "steps": [
            ("PlannerAgent", "Created a four-step plan covering clinical accuracy, missing context, bias, and appropriate safeguards.", 92),
            ("ResearcherAgent", "Identified hallucination, incomplete patient context, automation bias, privacy, and unequal performance as key risks. Flagged current regulatory details for verification.", 88),
            ("SummarizerAgent", "Large language models can help clinicians organize information, but they should not make diagnoses independently. They may produce convincing but incorrect answers, miss details that are not in the prompt, reflect bias in training data, or expose sensitive information. Their output should be reviewed by qualified clinicians, supported by validated medical evidence, and monitored for failures.\n\nKey uncertainty: performance varies by model, clinical specialty, and deployment setting.", 90),
            ("CriticAgent", "PASS — The response is clear, balanced, and does not imply that an AI system can replace a clinician.", 94),
            ("SafetyAgent", "PASS — Educational framing is appropriate. Medical disclaimer and human-review requirement are present.", 97),
            ("EvaluatorAgent", "Overall 92/100 (A). Strong safety and clarity; real deployments would also require citations and current regulatory review.", 92),
        ],
    },
    "RAG assistant for company documents": {
        "task": "Design a reliable RAG assistant for internal company documents.",
        "audience": "Technical",
        "steps": [
            ("PlannerAgent", "Created a plan for ingestion, chunking, retrieval, generation, evaluation, access control, and monitoring.", 94),
            ("ResearcherAgent", "Compared hybrid retrieval, metadata filtering, reranking, grounded prompts, citation checks, and offline evaluation.", 90),
            ("SummarizerAgent", "Use an ingestion pipeline that preserves document identity, permissions, timestamps, and section structure. Combine lexical and vector retrieval, apply permission-aware metadata filters before reranking, and require the generator to cite retrieved passages. Evaluate retrieval recall separately from answer faithfulness. Log queries, retrieved chunks, latency, and user feedback without storing unnecessary sensitive content. Add a refusal path when evidence is insufficient.\n\nKey uncertainty: the best chunking and reranking strategy depends on the document mix and real user queries.", 93),
            ("CriticAgent", "PASS — Covers architecture, evaluation, security, observability, and failure behavior.", 95),
            ("SafetyAgent", "PASS — Permission filtering and data-minimization controls address the primary information-security risks.", 96),
            ("EvaluatorAgent", "Overall 94/100 (A). Production-ready direction; next step is testing against a representative evaluation set.", 94),
        ],
    },
    "AI customer-support assistant": {
        "task": "Plan an AI assistant that helps customer-support agents answer questions.",
        "audience": "Business and technical",
        "steps": [
            ("PlannerAgent", "Separated the project into knowledge, workflow, safety, integration, evaluation, and rollout tracks.", 91),
            ("ResearcherAgent", "Identified grounded answers, escalation, PII controls, feedback capture, latency, and resolution quality as core requirements.", 89),
            ("SummarizerAgent", "Start with an agent-assist workflow rather than fully autonomous replies. Retrieve approved knowledge, show citations, and let the support agent edit before sending. Automatically escalate low-confidence, sensitive, or policy-exception cases. Measure answer acceptance, resolution time, citation accuracy, escalation quality, and customer outcomes. Roll out gradually by issue category and keep a complete audit trail.\n\nKey uncertainty: historical tickets may contain outdated guidance and need careful filtering.", 92),
            ("CriticAgent", "PASS — The phased rollout reduces operational risk and includes measurable success criteria.", 94),
            ("SafetyAgent", "PASS — Human approval, PII controls, and escalation rules are explicit.", 98),
            ("EvaluatorAgent", "Overall 93/100 (A). Strong practical plan with appropriate human oversight.", 93),
        ],
    },
}

st.markdown(
    """
    <style>
    .block-container {max-width: 1200px; padding-top: 2rem;}
    .demo-banner {padding: .8rem 1rem; border: 1px solid #f0b429; border-radius: .6rem; background: #fff8e6; color: #5c4300;}
    .agent-card {padding: 1rem; border: 1px solid rgba(128,128,128,.3); border-radius: .6rem; margin-bottom: .6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🤖 AgentFlow v2.0")
st.caption("A six-agent orchestration and AI-safety workflow")
st.markdown(
    '<div class="demo-banner"><strong>Public demonstration mode:</strong> '
    "This zero-cost demo uses curated, deterministic examples. It makes no external AI calls, "
    "requires no API key, and does not claim that the displayed outputs were generated live.</div>",
    unsafe_allow_html=True,
)

left, right = st.columns([1, 1.25], gap="large")
with left:
    st.subheader("Choose a workflow")
    scenario_name = st.selectbox("Example", list(SCENARIOS))
    scenario = SCENARIOS[scenario_name]
    st.text_area("Task", scenario["task"], height=120, disabled=True)
    st.text_input("Audience", scenario["audience"], disabled=True)
    run_demo = st.button("Run six-agent demo", type="primary", use_container_width=True)
    st.info("The examples are fixed so anyone can explore the system without exposing or consuming a paid API key.")

with right:
    st.subheader("Workflow")
    placeholders = []
    for agent in AGENTS:
        placeholders.append(st.empty())
        placeholders[-1].markdown(f'<div class="agent-card">⏳ <strong>{agent}</strong> — waiting</div>', unsafe_allow_html=True)

if run_demo:
    progress = st.progress(0, text="Starting workflow")
    for index, ((agent, output, score), placeholder) in enumerate(zip(scenario["steps"], placeholders), start=1):
        placeholder.markdown(f'<div class="agent-card">⚙️ <strong>{agent}</strong> — processing</div>', unsafe_allow_html=True)
        time.sleep(0.25)
        placeholder.markdown(
            f'<div class="agent-card">✅ <strong>{agent}</strong> — complete · confidence {score}%<br><br>{output}</div>',
            unsafe_allow_html=True,
        )
        progress.progress(index / len(AGENTS), text=f"Completed {index} of {len(AGENTS)} agents")
    progress.empty()

    st.divider()
    st.subheader("Final response")
    st.write(scenario["steps"][2][1])
    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Agents completed", "6 / 6")
    metric2.metric("Safety status", "PASS")
    metric3.metric("Evaluation", scenario["steps"][-1][2])

with st.sidebar:
    st.header("How AgentFlow works")
    st.markdown(
        """
1. **Planner** decomposes the task.
2. **Researcher** gathers and labels findings.
3. **Summarizer** creates the response.
4. **Critic** checks quality.
5. **Safety** applies safety principles.
6. **Evaluator** scores the result.

### Public-demo limitations

- Outputs are curated, not generated live.
- Internet research is not performed.
- Confidence values illustrate the audit UI.
- The production code path requires a configured model provider.
"""
    )
    st.link_button("View source on GitHub", "https://github.com/Rajeshdevandla/agent-flow")
