# ForgeAgent 完整架构文档

本文档为 **ForgeAgent** 全栈应用的核心架构参考，整合目录结构、技术栈、数据模型、Agent 执行流程与 API 设计。实现细节以运行后端 `GET /openapi.json` 为准。

---

## 一、项目概览

**ForgeAgent** 是面向开发者场景的 AI Agent 应用，采用 **Plan-and-Execute** 模式，具备规划、记忆、工具调用与执行四大核心能力。前端提供任务创建与可观测事件监控界面，后端基于 LangGraph 实现 Agent 运行时。

### 技术栈

| 层级 | 技术选型 |
|------|----------|
| **前端** | React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query + React Router |
| **后端** | Python 3.11+ + FastAPI + SQLAlchemy 2.0 (async) |
| **Agent 运行时** | LangGraph（主）+ LangChain（模型/工具/MCP 适配） |
| **数据库** | SQLite（AsyncEngine）+ 独立 LangGraph Checkpoint DB |
| **API 风格** | REST + SSE（Server-Sent Events） |

---

## 二、目录结构

```
ForgeAgent/
├── README.md                      # 项目总览
├── START.md                       # 快速开始指南
├── AGENTS.md                      # AI 协作规范
├── .env.example                   # 环境变量模板
│
├── frontend/                      # React + Vite + TypeScript
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx                # 应用入口
│       ├── main.tsx               # React DOM 入口
│       ├── api/                   # API 客户端封装
│       ├── components/            # 可复用 UI 组件
│       ├── views/                 # 页面级组件
│       ├── hooks/                 # 自定义 React Hooks
│       ├── store/                 # Zustand 状态管理
│       ├── router/                # React Router 配置
│       ├── types/                 # TypeScript 类型定义
│       ├── utils/                 # 工具函数
│       ├── constants/             # 常量定义
│       └── config/                # 前端配置
│
├── backend/                       # FastAPI 后端
│   ├── pyproject.toml
│   └── app/
│       ├── main.py                # FastAPI 入口（lifespan、路由、异常）
│       ├── core/                  # 横切基础设施
│       │   ├── config.py          # pydantic-settings 配置中心
│       │   ├── database.py        # AsyncEngine、session、init_db
│       │   ├── deps.py            # Depends（get_db 等）
│       │   ├── exceptions.py      # AppHTTPException
│       │   ├── llm_openai.py      # OpenAI 兼容客户端
│       │   ├── llm_retry.py       # LLM 重试机制
│       │   ├── circuit_breaker.py # 熔断器
│       │   └── workspace_config.py
│       ├── modules/               # Agent 核心模块
│       │   ├── execution/         # 执行引擎
│       │   ├── workflow/           # LangGraph 工作流
│       │   ├── planning/           # 规划模块
│       │   ├── memory/             # 记忆系统
│       │   ├── tools/              # 工具系统
│       │   └── prompts/            # 提示词管理
│       ├── services/               # 业务服务层
│       ├── repositories/           # 数据访问层
│       ├── models/                 # SQLAlchemy ORM
│       ├── schemas/                # Pydantic Schema
│       ├── api/v1/                 # API 路由
│       └── shared/                 # 共享工具
│
├── docs/                          # 文档目录
│   ├── README.md                  # 文档索引
│   ├── ARCHITECTURE.md            # 本文档
│   ├── architecture/               # 架构详细文档
│   ├── backend/                    # 后端相关文档
│   └── ...
│
├── skills/                        # Skill 工具定义
└── M-prompts/                     # 提示词模板
```

---

## 三、后端架构

### 3.1 分层设计

后端采用 **四层架构 + Agent 模块**，职责清晰、依赖单向：

```
┌─────────────────────────────────────────────────────────────────┐
│                        API 层 (api/v1/)                         │
│              路由定义、请求校验、响应序列化、SSE 推送            │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                      Service 层 (services/)                     │
│              业务编排、状态流转、事务边界、Agent 触发            │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────────┐
          │                       │                           │
          ▼                       ▼                           ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐
│ Repository 层   │    │  Agent Modules  │    │  Workflow (LangGraph)│
│ (repositories/) │    │ (modules/*)     │    │  (modules/workflow/) │
└────────┬────────┘    └────────┬────────┘    └──────────┬──────────┘
         │                     │                        │
         └─────────────────────┼────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Model 层 (models/) │
                    │   SQLAlchemy ORM      │
                    └─────────────────────┘
```

### 3.2 Agent 核心模块

#### 执行引擎 (`modules/execution/`)

| 文件 | 功能 |
|------|------|
| `step_react_loop.py` | **ReAct 循环执行核心** - Agent 主循环 |
| `step_executor.py` | 单步 step_start/ReAct/step_end，与 Actor 编排解耦 |
| `nodes.py` | Actor 节点定义（编排；单步执行委托 `step_executor`） |
| `tool_runner.py` | 工具运行器 |
| `llm_reply.py` | LLM 回复处理 |
| `stream_split.py` | 流式输出分割 |

#### 工作流管理 (`modules/workflow/`)

| 文件 | 功能 |
|------|------|
| `graph.py` | 图结构定义；`build_agent_graph` 可注入 planner/actor/learner，默认惰性加载 |
| `state.py` | 状态管理（TypedDict） |

#### 规划模块 (`modules/planning/`)

| 文件 | 功能 |
|------|------|
| `llm.py` | 规划用 LLM 接口 |
| `nodes.py` | 规划节点定义 |

#### 记忆系统 (`modules/memory/`)

| 文件 | 功能 |
|------|------|
| `session_blackboard.py` | 会话黑板（共享数据） |
| `session_context.py` | 会话上下文管理 |
| `conversation_summary.py` | 超长会话 LLM 摘要压缩 |
| `llm_context_budget.py` | LLM 消息 token 估算与预算截断 |
| `token_counter.py` | tiktoken 本地计数 |
| `tool_observation_compact.py` | Observation/轨迹 JSON 压缩 |
| `checkpointer.py` | 状态检查点 |
| `learner_node.py` | 学习者节点 |

#### 工具系统 (`modules/tools/`)

| 文件 | 功能 |
|------|------|
| `registry.py` | 工具注册表 |
| `builtin.py` | 内置工具定义 |
| `builtin_executor.py` | 内置工具执行器 |
| `mcp_sources.py` | MCP 工具源 |
| `skill_sources.py` | Skill 工具源 |

#### 提示词管理 (`modules/prompts/`)

| 文件 | 功能 |
|------|------|
| `step_react.py` | ReAct 模式提示词 |
| `planning.py` | 规划提示词 |
| `assistant_reply.py` | 助手回复提示词 |
| `learner_reflection.py` | 学习者反思提示词 |
| `catalog.py` | 提示词目录 |

### 3.3 数据模型

#### 数据库表

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `sessions` | 会话 | id(UUID), title, blackboard_notes_json, created_at |
| `messages` | 会话消息 | id(自增), session_id(FK), role, content, created_at |
| `tasks` | 任务 | id(UUID), session_id(FK), status, summary, plan_version, error_message |
| `task_events` | 任务事件流 | id(自增), task_id(FK), seq, ts, module, kind, payload_json |
| `settings_kv` | 键值配置 | key(PK), value_json, updated_at |

#### LangGraph Checkpoints

独立 SQLite 文件（`LANGGRAPH_CHECKPOINT_SQLITE_PATH`），通过 `AsyncSqliteSaver` 管理，支持任务恢复与状态持久化。

---

## 四、Agent 执行流程

### 4.1 Plan-Act-Learn 循环

```
┌─────────┐
│  START  │
└────┬────┘
     │
     ▼
┌─────────┐    ┌──────────────────────────────────────┐
│ planner │───▶│ SessionLLMContextManager 加载消息    │
└────┬────┘    │ + 黑板要点拼接                       │
     │         │ + plan_steps_with_llm               │
     │         │ + 写入 task_events (plan_created)   │
     │         └──────────────────────────────────────┘
     │
     ▼
┌─────────┐    ┌──────────────────────────────────────┐
│  actor  │───▶│ 逐步执行工具调用：                    │
└────┬────┘    │ - step_start → tool_call → tool_result → step_end │
     │         │ - 流式总结 llm_stream_delta          │
     │         │ - 支持 max_tool_failure_attempts     │
     │         └──────────────────────────────────────┘
     │
     ▼
┌─────────┐    ┌──────────────────────────────────────┐
│ learner │───▶│ 反思与黑板更新                        │
└────┬────┘    │ - 设置 replan_requested 或失败短路   │
     │         └──────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│                  条件边路由                       │
├─────────────────────────────────────────────────┤
│ outcome == failed?        → END                  │
│ replan_requested &&      → planner              │
│   未超 max_replan_attempts│ (bump plan_version) │
│ 否则                      → END                  │
└─────────────────────────────────────────────────┘
```

### 4.2 完整请求流程

```
客户端          API              Agent Runtime           数据库
   │              │                   │                    │
   │─POST /tasks──▶│                   │                    │
   │              ─┤ 验证会话           │                    │
   │              ─┤ 保存消息           │                    │
   │              ─┤ 创建任务           │                    │
   │              ◀┤ task_id            │                    │
   │◀─{task_id}────│                   │                    │
   │              ─┤ 触发异步执行 ─────────────────────────▶│
   │              │                   │                    │
   │              │            ┌──────┴──────┐             │
   │              │            │   LangGraph  │             │
   │              │            │   Planner     │             │
   │              │            │   Actor       │             │
   │              │            │   Learner     │             │
   │              │            └───────────────┘             │
   │              │                   │                    │
   │              ◀┤ 状态更新 ──────────────────────────────│
   │              │                   │                    │
   │─GET /events──▶│                   │                    │
   │◀─SSE events───│                   │                    │
```

---

## 五、API 设计

### 5.1 API 端点

| 路由 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/sessions` | POST | 创建会话 |
| `/api/v1/sessions` | GET | 列表会话 |
| `/api/v1/sessions/{id}` | GET | 获取会话详情 |
| `/api/v1/sessions/{id}/context` | GET | 会话上下文预览（黑板、规划消息窗口、token 粗估） |
| `/api/v1/sessions/{id}/messages` | GET | 获取会话消息 |
| `/api/v1/tasks` | POST | 创建任务 |
| `/api/v1/tasks` | GET | 列表任务 |
| `/api/v1/tasks/{id}` | GET | 获取任务详情 |
| `/api/v1/tasks/{id}` | PATCH | 更新任务（取消等） |
| `/api/v1/tasks/{id}/events` | GET | 获取任务事件 |
| `/api/v1/tasks/{id}/events/stream` | GET | SSE 事件流 |
| `/api/v1/tools` | GET | 获取工具列表 |
| `/api/v1/settings` | GET/PUT/PATCH/DELETE | 设置管理 |

### 5.2 SSE 事件类型

| kind | 说明 | payload 摘要 |
|------|------|--------------|
| `node_update` | LangGraph 节点更新 | module, node_name, state_snapshot |
| `plan_created` | 计划创建 | plan_version, steps[] |
| `tool_call` | 工具调用 | tool_name, arguments |
| `tool_result` | 工具结果 | tool_name, result |
| `step_start` | 步骤开始 | step_index, step |
| `step_end` | 步骤结束 | step_index, summary |
| `message` | 助手消息 | content, is_final |
| `error` | 错误 | error_message |
| `task_complete` | 任务完成 | status, final_summary |

---

## 六、前端架构

### 6.1 目录结构

```
frontend/src/
├── api/                    # API 客户端
│   ├── client.ts           # Axios 实例
│   ├── sessions.ts         # 会话 API
│   ├── tasks.ts            # 任务 API
│   └── settings.ts         # 设置 API
├── components/             # 可复用组件
│   ├── ui/                 # 基础 UI 组件
│   ├── chat/               # 聊天相关组件
│   ├── task/               # 任务相关组件
│   └── layout/             # 布局组件
├── views/                  # 页面级组件
│   ├── HomeView.tsx        # 首页
│   ├── SessionView.tsx     # 会话页面
│   ├── TaskDetailView.tsx  # 任务详情
│   └── SettingsView.tsx    # 设置页面
├── hooks/                  # 自定义 Hooks
│   ├── useSSE.ts           # SSE 连接管理
│   ├── useTasks.ts         # 任务状态管理
│   └── useSessions.ts      # 会话管理
├── store/                  # Zustand 状态
├── router/                 # React Router
├── types/                  # TypeScript 类型
├── utils/                  # 工具函数
├── constants/              # 常量
└── config/                 # 配置
```

### 6.2 核心功能

- **TanStack Query**：任务列表、事件查询的服务端状态管理
- **Zustand**：本地 UI 状态（如侧边栏折叠、主题）
- **SSE 事件处理**：`useSSE` Hook 管理 `EventSource` 连接与事件分发
- **实时更新**：任务状态与事件流的准实时同步

---

## 七、工具系统

### 7.1 工具来源

| 来源 | 说明 | 状态 |
|------|------|------|
| **Builtin** | 内置工具（搜索、文件操作等） | ✅ 已实现 |
| **MCP** | Model Context Protocol 工具 | 🔄 进行中 |
| **Skill** | Skill 定义的工具 | 🔄 进行中 |

### 7.2 内置工具

- `duckduckgo_search` - 网络搜索
- `list_tools` - 列出可用工具
- `read_file` - 读取文件
- `write_file` - 写入文件
- `shell` - 执行 Shell 命令
- `python_repl` - Python REPL

---

## 八、关键配置

### 8.1 环境变量

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | SQLite 数据库路径 |
| `LLM_API_KEY` | LLM API 密钥 |
| `LLM_BASE_URL` | LLM API Base URL |
| `LLM_MODEL` | LLM 模型名称 |
| `CORS_ORIGINS` | CORS 允许的源 |
| `LOG_LEVEL` | 日志级别 |
| `LANGGRAPH_CHECKPOINT_SQLITE_PATH` | LangGraph 检查点数据库 |

### 8.2 核心设置项

| Key | 说明 |
|-----|------|
| `mcp` | MCP 服务器配置 |
| `skills_paths` | Skill 工具路径列表 |

---

## 九、迭代路线

### 9.1 已完成 (MVP)

- ✅ 工具真实执行（Actor 按步调用）
- ✅ Session Memory 注入 Planner
- ✅ LangGraph Checkpoint 持久化
- ✅ LangGraph Streaming（节点级落库）

### 9.2 进行中 / 待完成

| 优先级 | TODO |
|--------|------|
| P0 | 任务取消与运行中协同 |
| P1 | 工具 Schema / 规划一体 |
| P1 | MCP 真实 Transport |
| P1 | Human-in-the-Loop |
| P2 | Skill 执行框架 |
| P2 | 自动化测试 |
| P3 | LangSmith / Tracing |
| P3 | 多 Agent 编排 |
| P4 | Settings 密钥加密 |
| P4 | WebSocket 替代 SSE |

---

## 十、相关文档

| 文档 | 说明 |
|------|------|
| [`docs/README.md`](README.md) | 文档索引 |
| [`docs/architecture/TECH_DESIGN.md`](architecture/TECH_DESIGN.md) | 技术设计细节 |
| [`docs/architecture/ARCH.md`](architecture/ARCH.md) | 目录与模块职责 |
| [`docs/backend/业务流程文档.md`](backend/业务流程文档.md) | 业务流程与伪代码 |
| [`docs/backend/TODO.md`](backend/TODO.md) | 后端迭代 TODO |
| [`START.md`](../START.md) | 快速开始 |
