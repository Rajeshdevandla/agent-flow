# AgentFlow 🤖

A multi-agent AI workflow system where specialized agents collaborate to complete complex tasks. Built with Amazon Bedrock and a clean agent architecture that's easy to extend.

---

## What this does

You give the system a task. Three AI agents work on it in sequence:

1. **Planner** — breaks the task into steps and identifies focus areas
2. **Researcher** — gathers information based on the plan
3. **Summarizer** — synthesizes everything into a clear final answer

You get back the final answer plus a full trace of what each agent contributed.

## Architecture

```
User Task
    │
    ▼
┌─────────────┐
│   Planner   │  Breaks task into steps
└──────┬──────┘
       │ plan
       ▼
┌─────────────┐
│ Researcher  │  Gathers information
└──────┬──────┘
       │ research
       ▼
┌─────────────┐
│ Summarizer  │  Writes final answer
└──────┬──────┘
       │
       ▼
  Final Report + Agent Trace
```

All agents share the same base class and Bedrock client. Each agent's output is passed as input to the next.

## Tech stack

| Component | Technology |
|-----------|-----------|
| LLM | Amazon Bedrock (Claude 3 Haiku) |
| Agent framework | Custom (no LangChain dependency) |
| API | FastAPI |
| Frontend | Streamlit |
| Containerization | Docker |

## Project structure

```
agent-flow/
├── config.py               # env var config
├── orchestrator.py         # runs the agent chain
├── agents/
│   ├── base.py             # shared base class for all agents
│   ├── planner.py          # task decomposition
│   ├── researcher.py       # information gathering
│   └── summarizer.py       # final synthesis
├── api/
│   └── main.py             # FastAPI routes
├── requirements.txt
├── .env.example
└── Dockerfile
```

## Getting started

```bash
git clone https://github.com/Rajeshdevandla/agent-flow.git
cd agent-flow
cp .env.example .env
# fill in your AWS credentials
pip install -r requirements.txt
uvicorn api.main:app --reload
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check, lists active agents |
| POST | /run | Run the workflow for a task |

**Example:**
```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Research and summarize the current state of quantum computing"}'
```

**Response shape:**
```json
{
  "task": "...",
  "final_answer": "...",
  "agent_trace": [
    {"agent": "Planner", "output": "..."},
    {"agent": "Researcher", "output": "..."},
    {"agent": "Summarizer", "output": "..."}
  ],
  "elapsed_seconds": 12.4
}
```

## Adding a new agent

1. Create a new file in `agents/` that inherits from `BaseAgent`
2. Implement the `run(self, input_data: dict) -> dict` method
3. Add it to `orchestrator.py`

The base class handles Bedrock API calls, so you just focus on the prompt logic.

## Notes

- Each agent makes one Bedrock API call, so a full workflow = 3 API calls
- The researcher doesn't call real web APIs — it uses the LLM's knowledge. Connecting to a search API would make this production-ready
- The agent trace is useful for debugging and for building an agent activity feed in the UI

---

Built as part of a GenAI portfolio for cloud/AI engineering roles.
