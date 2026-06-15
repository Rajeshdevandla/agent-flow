"""AgentFlow v2.0 Streamlit Frontend

Provides a live, interactive UI for the AgentFlow system.
Shows real-time agent workflow progress, decision logs, safety reports,
and quality scores.

Design decision: Streamlit chosen because it gets a functional demo UI
running in minimal code, which is important for showcasing the system.
"""

import os
import time
import json
from typing import Any

import streamlit as st
import anthropic

# Page configuration
st.set_page_config(
    page_title="AgentFlow v2.0",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
.agent-card {
    padding: 1rem;
    border-radius: 0.5rem;
    border: 1px solid #333;
    margin: 0.5rem 0;
}
.status-running { border-left: 4px solid #FFA500; }
.status-complete { border-left: 4px solid #00FF00; }
.status-failed { border-left: 4px solid #FF0000; }
.status-pending { border-left: 4px solid #666; }
</style>
""", unsafe_allow_html=True)


def initialize_client() -> anthropic.Anthropic | None:
    """Initialize Anthropic client from env or secrets."""
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def run_agent_step(
    client: anthropic.Anthropic,
    agent_name: str,
    system_prompt: str,
    user_message: str,
    status_placeholder: Any
) -> dict[str, Any]:
    """Run a single agent step and return structured result."""
    start_time = time.time()
    status_placeholder.markdown(
        f"**{agent_name}** - Running...",
        help=f"Processing with {agent_name}"
    )

    try:
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        result_text = response.content[0].text
        duration = time.time() - start_time

        status_placeholder.markdown(f"**{agent_name}** - Complete ({duration:.1f}s)")

        return {
            "agent": agent_name,
            "status": "complete",
            "output": result_text,
            "duration": duration,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens
        }
    except Exception as e:
        duration = time.time() - start_time
        status_placeholder.markdown(f"**{agent_name}** - Failed: {str(e)[:50]}")
        return {
            "agent": agent_name,
            "status": "failed",
            "output": f"Error: {str(e)}",
            "duration": duration,
            "tokens_used": 0
        }


def run_full_workflow(
    client: anthropic.Anthropic,
    task: str,
    user_type: str,
    workflow_col: Any
) -> dict[str, Any]:
    """Run the full 6-agent workflow with live status updates."""

    workflow_results = []
    status_placeholders = {}

    with workflow_col:
        st.subheader("Live Agent Workflow")

        # Create status placeholders for each agent
        agents = [
            "PlannerAgent",
            "ResearcherAgent",
            "SummarizerAgent",
            "CriticAgent",
            "SafetyAgent",
            "EvaluatorAgent"
        ]

        for agent in agents:
            placeholder = st.empty()
            placeholder.markdown(f"**{agent}** - Pending...")
            status_placeholders[agent] = placeholder

    # Step 1: PlannerAgent
    planner_result = run_agent_step(
        client,
        "PlannerAgent",
        "You are PlannerAgent. Break down tasks into 3-5 clear steps. "
        "Return JSON: {plan: [...], confidence: 0-100, reasoning: str}",
        f"Task: {task}",
        status_placeholders["PlannerAgent"]
    )
    workflow_results.append(planner_result)

    # Step 2: ResearcherAgent
    researcher_result = run_agent_step(
        client,
        "ResearcherAgent",
        "You are ResearcherAgent. Research and gather relevant information. "
        "Never make up facts. Return JSON: {findings: [...], confidence: HIGH/MEDIUM/LOW, "
        "key_uncertainties: [...]}",
        f"Task: {task}\nPlan: {planner_result['output'][:500]}",
        status_placeholders["ResearcherAgent"]
    )
    workflow_results.append(researcher_result)

    # Step 3: SummarizerAgent
    user_type_instruction = {
        "technical": "Use technical terminology, assume expert knowledge.",
        "non-technical": "Use simple language, no jargon, give examples.",
        "researcher": "Be thorough, cite sources, note limitations."
    }.get(user_type, "Use clear, accessible language.")

    summarizer_result = run_agent_step(
        client,
        "SummarizerAgent",
        f"You are SummarizerAgent. Summarize findings clearly. {user_type_instruction} "
        "Keep under 300 words. End with Key uncertainty: [biggest unknown]",
        f"Findings: {researcher_result['output'][:800]}",
        status_placeholders["SummarizerAgent"]
    )
    workflow_results.append(summarizer_result)

    # Step 4: CriticAgent
    critic_result = run_agent_step(
        client,
        "CriticAgent",
        "You are CriticAgent. Review this response for accuracy, completeness, "
        "consistency, clarity, and safety. Return JSON: "
        "{verdict: PASS/NEEDS_REVISION/FAIL, issues: [...], score: 0-100}",
        f"Response to review: {summarizer_result['output']}",
        status_placeholders["CriticAgent"]
    )
    workflow_results.append(critic_result)

    # Step 5: SafetyAgent
    safety_result = run_agent_step(
        client,
        "SafetyAgent",
        "You are SafetyAgent. Check this response for safety issues. "
        "Evaluate: harmful content, privacy violations, misinformation, "
        "manipulation, or inappropriate content. "
        "Return JSON: {action: PASS/WARN_USER/BLOCK, issues: [...], score: 0-100}",
        f"Content to check: {summarizer_result['output']}",
        status_placeholders["SafetyAgent"]
    )
    workflow_results.append(safety_result)

    # Step 6: EvaluatorAgent
    evaluator_result = run_agent_step(
        client,
        "EvaluatorAgent",
        "You are EvaluatorAgent. Score the overall workflow quality. "
        "Return JSON: {scores: {task_completion: 0-100, accuracy: 0-100, "
        "clarity: 0-100, safety: 0-100}, overall: 0-100, grade: A/B/C/D/F, "
        "summary: str}",
        f"Task: {task}\nFinal response: {summarizer_result['output'][:500]}",
        status_placeholders["EvaluatorAgent"]
    )
    workflow_results.append(evaluator_result)

    return {
        "task": task,
        "user_type": user_type,
        "workflow_results": workflow_results,
        "final_response": summarizer_result["output"],
        "safety": safety_result["output"],
        "evaluation": evaluator_result["output"],
        "total_tokens": sum(r["tokens_used"] for r in workflow_results),
        "total_time": sum(r["duration"] for r in workflow_results)
    }


def main():
    """Main Streamlit app."""
    st.title("AgentFlow v2.0")
    st.caption("Multi-Agent AI Workflow System powered by Anthropic Claude")

    # Initialize client
    client = initialize_client()
    if not client:
        st.error("ANTHROPIC_API_KEY not found. Add it to your .env file or Streamlit secrets.")
        st.stop()

    # Layout: left panel (input) and right panel (workflow)
    input_col, workflow_col = st.columns([1, 1])

    with input_col:
        st.subheader("Task Input")

        task = st.text_area(
            "What would you like to research or analyze?",
            placeholder="e.g., Explain the key differences between transformer and RNN architectures",
            height=120
        )

        user_type = st.selectbox(
            "Who is this for?",
            options=["technical", "non-technical", "researcher"],
            format_func=lambda x: {
                "technical": "Technical (developer/engineer)",
                "non-technical": "Non-technical (general audience)",
                "researcher": "Researcher (academic/expert)"
            }[x]
        )

        run_button = st.button("Run Workflow", type="primary", use_container_width=True)

    # Results tabs (shown after run)
    if run_button and task:
        with st.spinner("Running 6-agent workflow..."):
            results = run_full_workflow(client, task, user_type, workflow_col)

        # Display results in tabs
        st.divider()
        tab1, tab2, tab3, tab4 = st.tabs([
            "Final Response",
            "Decision Log",
            "Safety Report",
            "Quality Scores"
        ])

        with tab1:
            st.subheader("Final Response")
            st.markdown(results["final_response"])
            col1, col2 = st.columns(2)
            col1.metric("Total Time", f"{results['total_time']:.1f}s")
            col2.metric("Total Tokens", results["total_tokens"])

        with tab2:
            st.subheader("Decision Log")
            for step in results["workflow_results"]:
                with st.expander(
                    f"{step['agent']} - {step['status'].upper()} "
                    f"({step['duration']:.1f}s, {step['tokens_used']} tokens)"
                ):
                    st.code(step["output"][:1000], language="json")

        with tab3:
            st.subheader("Safety Report")
            st.code(results["safety"], language="json")

        with tab4:
            st.subheader("Quality Scores")
            st.code(results["evaluation"], language="json")

    elif run_button:
        st.warning("Please enter a task before running the workflow.")

    # Sidebar
    with st.sidebar:
        st.header("About AgentFlow v2.0")
        st.markdown("""A 6-agent AI pipeline with:
- Constitutional AI safety layer
- Decision logging for every step
- Quality evaluation after each run
- Configurable for different audiences

**Agents:**
1. PlannerAgent - Creates execution plan
2. ResearcherAgent - Gathers information
3. SummarizerAgent - Creates final response
4. CriticAgent - Reviews quality
5. SafetyAgent - Checks for safety
6. EvaluatorAgent - Scores overall quality
        """)
        st.caption("Built with Anthropic Claude")


if __name__ == "__main__":
    main()
