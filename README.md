# ForgeAgent

> 面向开发与使用场景的 AI Agent 应用（非通用编排框架）

## 核心特性

| 特性 | 说明 |
|------|------|
| **Plan-and-Execute** | 先规划后执行的 Agent 认知框架 |
| **四大模块** | 规划(Planning)、记忆(Memory)、工具(Tools)、执行(Execution) |
| **MCP 支持** | 支持 Model Context Protocol 工具扩展 |
| **Skill 上下文** | 支持 Skill 目录作为知识上下文注入 |
| **LangGraph** | 基于 LangGraph 的状态机工作流 |
| **实时监控** | 前端 SSE 实时展示任务执行状态 |

## 快速开始

```bash
# 前端
cd frontend && npm install && npm run dev

# 后端
cd backend
python -m venv .venv
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

详见 [START.md](START.md)

## 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    ForgeAgent                         │
├─────────────────────────────────────────────────────┤
│  Frontend (React + TypeScript + Vite)               │
│  ├── SSE 实时事件监控                               │
│  ├── Zustand 状态管理                               │
│  └── TailwindCSS + Radix UI                        │
├─────────────────────────────────────────────────────┤
│  Backend (Python + FastAPI + LangGraph)              │
│  ├── Plan-Execute 工作流                            │
│  ├── Session Memory + 黑板反思                      │
│  ├── Tool Registry (内置/MCP/Skill)                 │
│  └── SQLite + SQLAlchemy 2.0                       │
└─────────────────────────────────────────────────────┘
```

### Agent 工作流

```
Planner → Actor → Learner
    ↑                │
    └──── replan? ───┘
```

| 节点 | 职责 |
|------|------|
| **Planner** | 生成抽象计划步骤 |
| **Actor** | ReAct 循环执行，工具调用 |
| **Learner** | 反思轨迹，决定是否重规划 |

## 仓库结构

```
ForgeAgent/
├── frontend/          # React + TypeScript + Vite
├── backend/          # Python + FastAPI + LangGraph
├── docs/             # 详细文档
│   ├── getting-started/  # 入门指南
│   ├── architecture/    # 架构文档
│   ├── agent/           # Agent 核心
│   ├── optimization/    # 优化方案
│   └── api/             # API 文档
├── M-prompts/        # 方法提示词
└── skills/           # 技能目录
```

## 文档索引

| 分类 | 文档 | 说明 |
|------|------|------|
| 入门 | [docs/getting-started/README.md](docs/getting-started/README.md) | 文档索引 |
| 入门 | [docs/getting-started/QUICK-START.md](docs/getting-started/QUICK-START.md) | 快速开始 |
| 架构 | [docs/architecture/README.md](docs/architecture/README.md) | 架构索引 |
| 架构 | [docs/architecture/SYSTEM.md](docs/architecture/SYSTEM.md) | 系统架构 |
| 架构 | [docs/architecture/WORKFLOW.md](docs/architecture/WORKFLOW.md) | 工作流详解 |
| Agent | [docs/agent/README.md](docs/agent/README.md) | Agent 索引 |
| Agent | [docs/agent/PLANNING.md](docs/agent/PLANNING.md) | 规划模块 |
| Agent | [docs/agent/EXECUTION.md](docs/agent/EXECUTION.md) | 执行模块 |
| Agent | [docs/agent/MEMORY.md](docs/agent/MEMORY.md) | 记忆模块 |
| Agent | [docs/agent/CONTEXT.md](docs/agent/CONTEXT.md) | 上下文管理 |
| 优化 | [docs/optimization/README.md](docs/optimization/README.md) | 优化索引 |
| 优化 | [docs/optimization/PERFORMANCE.md](docs/optimization/PERFORMANCE.md) | 性能优化 |
| 优化 | [docs/optimization/PROMPT.md](docs/optimization/PROMPT.md) | 提示词优化 |
| API | [docs/api/README.md](docs/api/README.md) | API 索引 |
| API | [docs/api/REFERENCE.md](docs/api/REFERENCE.md) | API 参考 |

## License

见 [LICENSE](LICENSE)
