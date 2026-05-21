# ForgeAgent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-1c3c3c?logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![MCP](https://img.shields.io/badge/Protocol-MCP-6e3b8b)](https://modelcontextprotocol.io/)

**面向开发与使用场景的 AI Agent 应用** — 非通用编排框架，而是专注「规划、记忆、工具、执行」四大核心能力的即用型 Agent。

**An AI Agent application built for development & usage scenarios** — not a generic orchestration framework, but a ready-to-use agent with four integrated capabilities: Planning, Memory, Tools, and Execution.

## 核心特性 | Core Features

- **Plan-and-Execute** — 先规划后执行的认知主循环，配合 Learner 反思重规划
- **统一工具注册表** — 内置工具、MCP 远程工具、Skill 知识上下文统一管理
- **RAG 知识库** — 向量检索 + BM25 混合召回，支持重排序与增量索引
- **SSE 实时监控** — 前端时间线实时展示任务计划、步骤执行与事件流
- **会话记忆** — 黑板反思 + 对话摘要 + 上下文裁剪，适应长任务窗口
- **人工中断** — 危险操作审批流，执行中可介入

## 快速开始 | Quick Start

```bash
# 前端 | Frontend
cd frontend && npm install && npm run dev

# 后端 | Backend
cd backend
python -m venv .venv
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

> 详细安装说明见 [START.md](START.md)，AI 协作规范见 [AGENTS.md](AGENTS.md)

## 架构 | Architecture

```
User Input → Planner → Actor (ReAct Loop) → Learner
                ↑                              │
                └───────── replan? ────────────┘
                          │
                    [END] ✓
```

| 节点 | 职责 |
|------|------|
| **Planner** | 理解用户意图，生成抽象计划步骤 |
| **Actor** | ReAct 循环执行：思考 → 工具调用 → 观察 → 迭代 |
| **Learner** | 反思执行轨迹，决定是否重规划或结束 |

### 技术栈 | Tech Stack

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Vite + TailwindCSS + Radix UI |
| 状态管理 | Zustand |
| 后端 | Python 3.11+ / FastAPI + SQLAlchemy 2.0 (async) |
| Agent 运行时 | LangGraph (状态机) + LangChain |
| 数据库 | SQLite + LangGraph Checkpointer |
| LLM | OpenAI 兼容接口 (OpenAI / Anthropic / 任意兼容服务) |

## 仓库结构 | Repository Structure

```
ForgeAgent/
├── frontend/           # React + TypeScript + Vite + TailwindCSS
│   └── src/
│       ├── api/        # API 客户端
│       ├── components/ # UI 组件
│       ├── views/      # 页面视图
│       ├── store/      # Zustand 状态
│       └── types/      # TypeScript 类型
├── backend/            # Python + FastAPI + LangGraph
│   └── app/
│       ├── api/        # REST API 路由 (v1)
│       ├── core/       # 配置、数据库、LLM 客户端
│       ├── models/     # SQLAlchemy 数据模型
│       ├── modules/    # Agent 核心模块
│       │   ├── planning/   # 规划模块
│       │   ├── execution/  # 执行引擎 (ReAct)
│       │   ├── memory/     # 会话记忆 & RAG
│       │   ├── tools/      # 工具注册表 & MCP 客户端
│       │   └── workflow/   # LangGraph 图定义
│       ├── repositories/   # 数据访问层
│       ├── schemas/        # Pydantic 模型
│       └── services/       # 业务逻辑
├── docs/               # 文档 (入门、架构、Agent 模块、优化、API)
├── M-prompts/          # 方法提示词模板
├── skills/             # Skill 知识目录
├── START.md            # 初始化与启动
├── AGENTS.md           # AI 协作规范
└── LICENSE
```

## 文档索引 | Docs

| 文档 | 说明 |
|------|------|
| [docs/入门指南/](docs/入门指南/) | 安装配置、快速开始 |
| [docs/架构/](docs/架构/) | 系统架构、工作流、数据模型 |
| [docs/Agent核心/](docs/Agent核心/) | 规划、执行、记忆、上下文、RAG |
| [docs/优化/](docs/优化/) | 性能、提示词、上下文优化 |
| [docs/接口/](docs/接口/) | API 参考 |
| [docs/面试/](docs/面试/) | Agent 核心、业务流程、技术难点 |

## License

MIT — 详见 [LICENSE](LICENSE)
