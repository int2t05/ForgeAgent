# ForgeAgent

**AI Agent Application for Development and Usage Scenarios** (not a general-purpose orchestration framework): **Planning, Memory, Tools, Execution** four core capabilities, **Plan-and-Execute** main loop; frontend for task and observable event monitoring.

> This project is not a general-purpose Agent orchestration framework, but an AI Agent application optimized for specific scenarios.

## Core Features

| Feature | Description |
|---------|-------------|
| **Plan-and-Execute** | Agent cognitive framework with plan-first-then-execute |
| **Four Modules** | Planning, Memory, Tools, Execution |
| **MCP Support** | Model Context Protocol tool extension |
| **Skill Context** | Skill directory as knowledge context injection |
| **LangGraph** | LangGraph-based state machine workflow |
| **Real-time Monitoring** | Frontend SSE for real-time task execution status |

## Repository Structure

This is a **monorepo** with `frontend/` (Node/React) and `backend/` (Python/FastAPI) **in separate directories**.

```
ForgeAgent/
├── frontend/              # React + TypeScript + Vite + TailwindCSS
│   └── src/
│       ├── api/          # API client
│       ├── components/   # React components
│       ├── views/        # Page views
│       ├── store/        # Zustand state management
│       └── types/        # TypeScript types
│
├── backend/              # Python 3.11+ + FastAPI + LangGraph
│   └── app/
│       ├── api/          # REST API routes
│       ├── core/         # Core configuration
│       ├── models/       # Data models
│       ├── modules/      # Agent modules
│       │   ├── execution/   # Execution engine
│       │   ├── memory/      # Memory management
│       │   ├── planning/    # Planning module
│       │   ├── prompts/     # Prompt templates
│       │   ├── tools/       # Tool system
│       │   └── workflow/    # Workflow definition
│       ├── repositories/  # Data access layer
│       ├── schemas/       # Pydantic models
│       └── services/      # Business logic
│
├── docs/                 # Detailed documentation
├── M-prompts/           # Method prompt templates
└── skills/              # Skill directory
```

## Quick Start

See **[`START.md`](START.md)** for detailed installation, environment variables, and startup commands.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/Mac: source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Environment Variables

Copy the environment template from the repository root:

```bash
# Windows
copy .env.example .env
# Linux/Mac
cp .env.example .env
```

Edit `.env` to fill in necessary API keys and configurations. **Do NOT commit `.env` with real keys to Git**.

## Documentation Index

| Document | Description |
|----------|-------------|
| [`START.md`](START.md) | Scaffold installation, startup steps |
| [`AGENTS.md`](AGENTS.md) | AI collaboration and engineering standards |
| [`docs/README.md`](docs/README.md) | Complete documentation index |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture |
| [`docs/02-task-processing-flow.md`](docs/02-task-processing-flow.md) | Task processing flow |
| [`docs/03-agent-planning.md`](docs/03-agent-planning.md) | Agent planning module |
| [`docs/04-agent-memory.md`](docs/04-agent-memory.md) | Agent memory module |
| [`docs/05-agent-tool-usage.md`](docs/05-agent-tool-usage.md) | Agent tool usage |
| [`docs/06-agent-execution.md`](docs/06-agent-execution.md) | Agent execution module |
| [`docs/07-context-management.md`](docs/07-context-management.md) | Context management |
| [`docs/08-agent-response-optimization.md`](docs/08-agent-response-optimization.md) | Response optimization |
| [`docs/backend/TODO.md`](docs/backend/TODO.md) | Backend iteration TODO |
| [`docs/agent-framework-optimization.md`](docs/agent-framework-optimization.md) | Framework optimization |
| [`docs/performance-optimization.md`](docs/performance-optimization.md) | Performance optimization |
| [`docs/prompt-optimization.md`](docs/prompt-optimization.md) | Prompt optimization |
| [`docs/context-management.md`](docs/context-management.md) | Context management optimization |

## System Architecture

### Agent Workflow

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────┐
│              LangGraph Agent Workflow                │
│                                                      │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ Planner │───▶│  Actor  │───▶│ Learner │         │
│  └─────────┘    └─────────┘    └─────────┘         │
│       ▲                              │               │
│       │         ┌────────────────────┘              │
│       └─────────│  Conditional: replan or done      │
│                 └──────────────────────────────────▶ END
└─────────────────────────────────────────────────────┘
```

| Node | Responsibility |
|------|----------------|
| **Planner** | Generate abstract plan steps |
| **Actor** | Iterate and execute plans, ReAct loop |
| **Learner** | Reflect on execution trace, decide replanning |

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend Framework | React 18 + TypeScript + Vite |
| UI Library | TailwindCSS + Radix UI |
| State Management | Zustand |
| Backend Framework | FastAPI + SQLAlchemy 2.0 (async) |
| Agent Framework | LangGraph |
| Database | SQLite |
| LLM | OpenAI / Anthropic |

## License

See [`LICENSE`](LICENSE) in repository root.
