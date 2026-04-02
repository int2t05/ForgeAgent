# ForgeAgent 全栈架构设计（MVP）

本文档定义 ForgeAgent 前后端**目录结构与模块职责**；与 [`TECH_DESIGN.md`](./TECH_DESIGN.md) 数据模型与 API 方向、后端 **`GET /openapi.json`** 暴露的契约一致。若仓库中另行维护 PRD / 分阶段指南，以其为准；当前文档索引见 [`docs/README.md`](../README.md)。**不含可运行代码。**

---

## 一、后端架构

### 1. 分层设计思想

后端采用 **四层架构**，自上而下职责递减、依赖单向：

```
HTTP 层（api/）→ 服务层（services/）→ 仓储层（repositories/）→ 模型层（models/）
                     ↕
       modules/workflow（LangGraph 编排）⟷ modules/tools（统一工具注册表）
                     ↕
    modules/planning · modules/execution · modules/memory（Plan-Act-Learn：Planner / Actor / Learner）
```

| 层级 | 职责 | 规则 |
|------|------|------|
| **API 层** | 路由定义、请求校验、响应序列化、SSE 推送 | 仅调用 Service；禁止直接操作 DB Session |
| **服务层** | 业务编排、状态流转、事务边界 | 可调用多个 Repository；可触发 Agent 执行 |
| **仓储层** | 单表 CRUD 与查询封装 | 仅操作 SQLAlchemy AsyncSession；不含业务判断 |
| **模型层** | ORM 声明式模型 + Pydantic Schema | ORM 与 Schema 分离，互不依赖 |
| **workflow** | `modules/workflow`：LangGraph 状态与编译图 | 串联 planning / execution 节点；由服务层触发 |
| **业务子模块** | `modules/planning`、`execution`、`tools`、`memory` | 规划、执行、工具元数据、记忆域扩展点 |

### 2. 后端文件结构

```
backend/
├── pyproject.toml
├── app/
│   ├── main.py                             # FastAPI：lifespan、路由、异常处理；GET /health
│   ├── core/                               # 横切基础设施（与业务子模块解耦）
│   │   ├── config.py                       # pydantic-settings
│   │   ├── database.py                     # AsyncEngine、session、init_db
│   │   ├── deps.py                         # get_db 等 Depends
│   │   ├── exceptions.py                   # AppHTTPException
│   │   └── llm_openai.py                  # OpenAI 兼容客户端构造、密钥探测（规划/执行复用）
│   │
│   ├── modules/                            # 按 PRD 四能力 + 编排拆分，便于单测与替换实现
│   │   ├── planning/                      # 规划：LLM 出步骤、planner / replan 节点
│   │   ├── memory/                        # 记忆：会话上下文加载、Learner、黑板持久化、LangGraph checkpointer
│   │   ├── tools/                         # 工具：registry、builtin、mcp_sources、skill_sources
│   │   ├── execution/                     # 执行：Actor 节点（逐步工具 + 流式总结）、路由边
│   │   └── workflow/                      # LangGraph：state.py、graph.py（编译图单例）
│   │
│   ├── models/                            # SQLAlchemy ORM
│   ├── schemas/                           # Pydantic API 契约
│   ├── api/v1/                            # REST + SSE 路由；不含 deps（deps 在 core）
│   ├── services/                          # 用例编排（task、session、settings、events、tools）
│   └── repositories/                      # 按表封装 AsyncSession 访问
│
├── tests/
├── scripts/
└── data/                                   # SQLite（.gitignore）
```

### 3. 后端各模块详细说明

#### 3.1 `app/main.py` — 应用入口

- 创建 FastAPI 实例，配置 `title`、`version`
- 定义 `lifespan` 异步上下文管理器：启动时初始化数据库（`create_all` 或 Alembic）、按 `settings_kv` 刷新工具注册表、打开 LangGraph checkpointer 并 **`init_compiled_agent_graph`**；关闭时 **`close_langgraph_checkpointer`**、释放图单例后再 `dispose` ORM 引擎
- 挂载 CORS 中间件（`CORS_ORIGINS` 环境变量控制）
- 注册 `/health` 路由与 `/api/v1` 路由组

#### 3.2 `app/core/config.py` — 配置中心

- 使用 `pydantic-settings` 的 `BaseSettings` 读取环境变量
- 统一管理：`DATABASE_URL`、`LLM_API_KEY`、`CORS_ORIGINS`、`LOG_LEVEL`、`MAX_REPLAN_ATTEMPTS` 等
- 提供单例访问，通过 FastAPI 依赖注入分发

#### 3.3 `app/core/database.py` — 数据库引擎

- 创建 `AsyncEngine`（`sqlite+aiosqlite`）
- 提供 `async_sessionmaker` 工厂
- 暴露 `init_db()` 用于 lifespan 初始化建表
- MVP 阶段使用 `metadata.create_all`；后续可切换 Alembic 迁移

#### 3.4 `app/models/` — ORM 模型

| 文件 | 对应表 | 关键字段 |
|------|--------|----------|
| `base.py` | — | `DeclarativeBase`；可选 mixin 提供 `id`、`created_at`、`updated_at` |
| `task.py` | `tasks` | `id(UUID)`、`session_id`、`status`、`summary`、`plan_version`、`error_message` |
| `task_event.py` | `task_events` | `id(自增)`、`task_id(FK)`、`seq`、`ts`、`module`、`kind`、`payload_json` |
| `session.py` | `sessions` | `id(UUID)`、`title`、`blackboard_notes_json`、`created_at` |
| `message.py` | `messages` | `id(自增)`、`session_id(FK)`、`role`、`content`、`created_at` |
| `setting.py` | `settings_kv` | `key(PK)`、`value_json`、`updated_at` |

索引策略：`task_events` 上建 `(task_id, seq)` 联合唯一索引。

#### 3.5 `app/schemas/` — Pydantic Schema

与 OpenAPI（运行态 `/openapi.json`）及 `app/schemas/` 实现严格对齐：

- `common.py`：`ErrorResponse(detail, code?)`、`PaginatedResponse(items, total)` 泛型基类
- `task.py`：`TaskCreate(session_id, user_message)`、`TaskCreateResponse(task_id, events_stream_path)`、`TaskResponse`、`TaskListResponse`
- `event.py`：`EventResponse(seq, ts, module, kind, payload)`、`EventListResponse`
- `session.py`：`SessionCreate(title?)`、`SessionCreateResponse(session_id)`
- `message.py`：`MessageResponse(id, role, content, created_at)`
- `setting.py`：`SettingsResponse`、`SettingsUpdate`（禁止含密钥字段）
- `tool.py`：`ToolInfo(name, description, source, read_only?)`、`ToolListResponse`

#### 3.6 `app/api/` — 路由层

| 文件 | 路由前缀 | 核心端点 |
|------|----------|----------|
| `main.py` | `/` | `GET /health` |
| `v1/tasks.py` | `/api/v1/tasks` | `POST` 创建任务、`GET` 列表/详情/事件、`GET …/events/stream` SSE |
| `v1/sessions.py` | `/api/v1/sessions` | 会话 CRUD、消息列表与编辑 |
| `v1/settings.py` | `/api/v1/settings` | `GET` / `PUT` / `PATCH` / `DELETE` 非密钥设置 |
| `v1/tools.py` | `/api/v1/tools` | `GET` 工具注册表 |
| `v1/router.py` | `/api/v1` | 聚合子路由 |

依赖注入见 **`app/core/deps.py`**（`get_db` 等），由路由 `Depends` 引用，不属于 `api/` 包。

#### 3.7 `app/services/` — 业务逻辑层

| 文件 | 核心职责 |
|------|----------|
| `task_service.py` | 创建任务（写 tasks + messages）→ 加载黑板种子 / 异步调度编译图（`thread_id=task_id`）→ 完成后 flush 黑板；列表与详情；取消/终态 |
| `event_stream_service.py` | 事件增量查询与 SSE 推送 |
| `session_service.py` | 会话创建与查询 |
| `settings_service.py` | KV 配置读写；写入时过滤禁止的密钥字段 |
| `tool_service.py` | 从 `ToolRegistry` 实例获取已注册工具列表 |

#### 3.8 `app/repositories/` — 数据访问层

每个 Repository 封装对应表的数据库操作（实现文件名为 `*_repository.py`，如 `task_repository.py`、`event_repository.py`）：

- 接收 `AsyncSession` 作为参数
- 仅包含数据读写逻辑，不含业务判断
- 提供类型安全的返回值（ORM Model 实例或标量）
- 查询方法支持分页参数（`limit`、`offset`）

#### 3.9 `app/modules/workflow` + `planning` + `execution` + `memory` — Plan-Act-Learn

| 位置 | 职责 |
|------|------|
| `workflow/state.py` | `AgentState(TypedDict)`：`task_id`、`session_id`、`user_message`、`plan_steps`、`replan_count` / `max_replan_attempts`、`blackboard_notes`、`actor_tool_trace`、`replan_requested`、`outcome`、`summary` 等 |
| `workflow/graph.py` | `build_agent_graph`：`START` → `planner` → `actor` → `learner` → 条件边 → `planner` 或 `END`；`init_compiled_agent_graph(checkpointer)` 在 lifespan 中注入持久化 saver |
| `planning/llm.py` | 规划用 LLM 调用与计划 JSON 解析 |
| `planning/nodes.py` | `planner_node`：会话消息（`SessionLLMContextManager`）+ 黑板要点注入；若 `replan_requested` 则先 bump `plan_version` 并写 `replan` 事件；`initial_force_replan_budget`（测试令牌） |
| `execution/nodes.py` | `actor_node`：按步 `tool_call` / `tool_result` / `step_end`，可选仅 `step_start` 的强制重规划预算；流式总结写 `llm_stream_delta`；`route_after_learner`（兼容别名 `route_after_actor` / `route_after_executor`） |
| `execution/llm_reply.py` | Actor 收尾阶段流式助手回复（thinking / answer） |
| `execution/stream_split.py` | think/answer 流式分段（若仍被回复管线引用） |
| `memory/learner_node.py` | Learner：反思与黑板更新、失败短路、`replan_requested` |
| `memory/session_blackboard.py` | 黑板与 `sessions.blackboard_notes_json` 同步；任务结束从 checkpoint flush |
| `memory/session_context.py` | `SessionLLMContextManager`：加载最近会话消息为 LangChain `ChatMessage` 列表 |
| `memory/checkpointer.py` | `open_langgraph_checkpointer` / `close_langgraph_checkpointer`；默认 `AsyncSqliteSaver`，可选 Postgres |

**LangGraph 主图结构**（与实现一致）：

```
[START] → planner → actor → learner → (replan?) → planner …
                                    └─ (done) ──→ [END]
```

#### 3.10 `app/modules/tools/` — 统一工具注册表

| 文件 | 职责 |
|------|------|
| `registry.py` | `ToolRegistry`：合并内置 / MCP mock 元数据 / Skill manifest，`refresh(db)` |
| `builtin.py` | 内置工具 `ToolItem` 列表 |
| `mcp_sources.py` | 自设置解析 MCP 项（含 mock transport） |
| `skill_sources.py` | 扫描 `manifest.json` → `ToolItem(source="skill")` |

#### 3.11 `app/core/` — 横切基础设施（当前实现）

| 文件 | 职责 |
|------|------|
| `config.py` | `Settings` / `get_settings()` |
| `database.py` | `AsyncEngine`、`AsyncSessionLocal`、`init_db` / `close_db` / `get_db` |
| `deps.py` | `get_db` 再导出（路由 `Depends` 入口） |
| `exceptions.py` | `AppHTTPException`，与 `main.py` 中 handler 一致 |
| `llm_openai.py` | `is_llm_configured`、`build_chat_model`（规划与执行复用） |

#### 3.12 `app/shared/` — 跨层复用小件（无业务、无 I/O）

| 文件 | 职责 |
|------|------|
| `payload.py` | `payload_json_to_dict`：事件 `payload_json` 安全解析 |
| `utc_datetime.py` | `UtcDateTime`：SQLite 读出 naive UTC 时补全 tzinfo，供 ORM 列类型使用 |

与 `app/core/` 区分：`core` 管配置、数据库、依赖与进程级能力；`shared` 仅放纯函数与可复用类型，避免与「基础设施」混放。

### 4. 后端关键数据流

```
用户请求 POST /api/v1/tasks
  → api/v1/tasks.py（校验 Schema）
    → services/task_service.py（创建 Task + Message，独立会话提交）
      → repositories/task_repository.py、message_repository.py 等
      → asyncio.create_task：独立会话执行 LangGraph（configurable `thread_id` = task_id）
        → modules/workflow/graph.py（get_compiled_agent_graph；`astream(..., stream_mode="updates")`）
          → modules/planning/nodes.py（planner）
          → modules/planning/llm.py（计划 JSON）
          → modules/execution/nodes.py（actor：工具执行 + 流式总结）
          → modules/memory/learner_node.py（learner）
          → task_service 将每次节点完成的增量映射为 `module=workflow`、`kind=node_update`
          → modules/tools/registry.py（工具元数据与 `execute`）
        → 业务事件仍经 repositories/event_repository.py 追加 task_events（seq 单调）
        → 任务前后可 `load_blackboard_seed` / `flush_blackboard_from_graph_checkpoint`（黑板与会话行对齐）
      → task_repository 更新任务终态 success / failed / cancelled
  ← 返回 { task_id, events_stream_path }（字段名以 OpenAPI 为准）

GET …/events/stream（SSE）
  → services/event_stream_service.py
    → 轮询已提交的 task_events（seq > last_sent）；终态后空闲若干轮关闭流
  ← text/event-stream（不依赖内存事件总线；断线后可 REST 按 after_seq 补拉）
```

---

## 二、前端架构

### 1. 分层设计思想

前端采用 **页面 → 组件 → Hook → API → Store** 分层：

```
Pages（页面容器）→ Components（可复用 UI）
    ↓                    ↓
  Hooks（数据逻辑）→ API（请求函数）→ 后端
    ↓
  Stores（轻量全局状态）
```

| 层级 | 职责 | 规则 |
|------|------|------|
| **Pages** | 路由级页面容器，组合 Components 与 Hooks | 一个路由对应一个页面文件 |
| **Components** | 可复用的 UI 组件，职责单一 | 不直接调用 API；通过 props 或 hooks 获取数据 |
| **Hooks** | 数据获取与状态逻辑（TanStack Query 封装） | 封装 query/mutation；SSE 订阅与增量合并 |
| **API** | HTTP 请求函数，与后端契约对齐 | 纯函数；仅负责请求/响应转换 |
| **Stores** | Zustand 轻量全局状态 | 仅存放跨页面共享的客户端状态（如 session_id） |
| **Types** | TypeScript 类型定义 | 与后端 Schema / OpenAPI 对齐 |

### 2. 前端文件结构

前端按 **分层目录** 组织：**页面**（`views/`）、**布局**（`layouts/`）、**可复用组件**（`components/<域|ui>/`）、**数据层**（`api/`、`hooks/`、`store/`）、**类型与工具**（`types/`、`utils/`）、**配置与常量**（`config/`、`constants/`），以及 **`plugins/`**（第三方库装配）。路径别名 **`@/`** 指向 `src/`（见 `frontend/vite.config.ts` / `tsconfig`）。路由级页面在 `router/index.tsx` 中使用 `React.lazy` 做代码分割；`App.tsx` 以 `Suspense` 包裹 `RouterProvider` 作为懒加载兜底。

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig*.json
├── eslint.config.js
├── public/
│
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    │
    ├── assets/                            # 静态资源（图片、字体等）
    ├── config/
    │   └── env.ts                          # 与构建/运行时相关的配置（如 VITE_API_BASE_URL）
    ├── constants/
    │   ├── index.ts                        # 聚合导出
    │   └── task.ts                        # 分页默认值、任务状态 UI 映射等
    │
    ├── types/                              # 与 OpenAPI / TECH_DESIGN 对齐的 TS 类型
    │   ├── api.ts
    │   ├── task.ts、session.ts、settings.ts、mcp.ts、tool.ts
    │   └── …
    │
    ├── api/                                # HTTP 请求函数（按资源拆分文件）
    │   ├── client.ts                       # baseURL、统一错误解析
    │   ├── sessions.ts、settings.ts、tasks.ts、sse.ts、tools.ts
    │   └── …
    │
    ├── utils/                              # 纯函数、流式/事件解析、日期与文案工具（原 core/lib）
    │
    ├── hooks/                              # TanStack Query、SSE 等数据 Hooks（全仓平铺，按文件名区分域）
    ├── store/                              # Zustand：sessionStore、composerTaskStore、导航侧栏等
    │
    ├── layouts/                            # AppLayout、Sidebar、Header、PendingComposerTaskSync
    │
    ├── components/
    │   ├── ui/                             # LoadingSpinner、ErrorAlert、EmptyState、ConfirmDialog
    │   ├── chat/                           # ChatMarkdown、SessionListPanel、SidebarChatHistory
    │   ├── task/                           # TaskTimeline、TaskPlanSteps、TaskEventRow
    │   └── settings/                       # 如 McpServersEditor
    │
    ├── views/                              # 路由页面：ChatPage、HomePage、TaskListPage、…
    ├── router/
    │   └── index.tsx                       # createBrowserRouter + 页面 lazy
    │
    ├── plugins/                            # 第三方注册/工厂（如 TanStack Query 默认 Client）
    └── directives/                         # 预留（React 无模板指令；可放横切 HOC/包装器）
```

### 3. 前端各模块详细说明

#### 3.1 `src/App.tsx` — 根组件

- 包裹 `QueryClientProvider`（TanStack Query，客户端工厂见 `plugins/react-query.ts`）
- 以 `Suspense` 包裹 `RouterProvider`，承接路由级 `lazy` 页面
- 包裹 `RouterProvider`（React Router）
- 全局错误边界

#### 3.2 `src/router/index.tsx` — 路由配置

| 路由 | 页面组件 | 说明 |
|------|----------|------|
| `/` | `views/ChatPage`（`lazy`） | 对话首页（`index`） |
| `/overview` | `views/HomePage`（`lazy`） | 概览 / 仪表盘 |
| `/chat` | — | 重定向到 `/` |
| `/chat/history` | `views/SessionHistoryPage`（`lazy`） | 会话历史 |
| `/tasks` | `views/TaskListPage`（`lazy`） | 任务列表 |
| `/tasks/:taskId` | `views/TaskDetailPage`（`lazy`） | 任务详情（计划 + 时间线） |
| `/settings` | `views/SettingsPage`（`lazy`） | 设置 |
| `*` | `views/NotFoundPage`（`lazy`） | 404 |

以上均包裹在 `AppLayout`（`layouts/AppLayout.tsx`）下。

#### 3.3 `src/api/` — 请求层

| 位置 | 职责 |
|------|------|
| `api/client.ts` | `baseURL`（来自 `config/env.ts`）、统一错误解析（`ErrorResponse`）；各 API 模块共用 |
| `api/tasks.ts` | 任务 CRUD、事件列表 REST |
| `api/sse.ts` | 任务事件 SSE 订阅与重连 |
| `api/sessions.ts` | 会话与消息 |
| `api/settings.ts` | 设置读写 |
| `api/tools.ts` | 工具注册表列表 |

#### 3.4 `src/hooks/` — 数据 Hooks

| 域（约定） | 文件 | 核心逻辑 |
|------|------|----------|
| tasks | `useTasks.ts` | 任务列表 Query（分页、筛选） |
| tasks | `useTaskDetail.ts` | 单任务详情 |
| tasks | `useTaskTimeline.ts` | REST 首屏 + SSE 增量；按 `seq` 排序去重；断线 `after_seq` 补拉 |
| tasks | `usePendingComposerTask.ts` | 与全局「正在编排的任务」横幅/状态联动 |
| sessions | `useSession.ts` | `session_id` 与 `sessionStorage` / 自动建会话 |
| settings | `useSettings.ts` | 设置 Query + Mutation |
| tools | `useTools.ts` | 工具列表 Query |

#### 3.5 `src/views/` — 页面组件

| 页面 | 核心区块 | 数据依赖 |
|------|----------|----------|
| `ChatPage` | 会话侧栏 + 对话与流式展示 | `useSession`、`api/sessions`、任务编排相关 Hooks |
| `HomePage` | 最近任务 + 快捷发起任务 | `useTasks(limit=5)`、`useSession`、`createTask` |
| `TaskListPage` | 列表与筛选 | `useTasks` |
| `TaskDetailPage` | 状态、计划、时间线 | `useTaskDetail`、`useTaskTimeline` |
| `SettingsPage` | MCP / Skills 等 | `useSettings` |
| `NotFoundPage` | 404 | 无 |

#### 3.6 `src/components/` — 组件分组

按 **功能域** 分子目录（`chat/`、`task/`、`settings/`）；与页面解耦的通用 UI 放在 **`components/ui/`**。

#### 3.7 Zustand：`sessionStore` 与 `composerTaskStore`

- **`store/sessionStore.ts`**：当前 `session_id`（可与 `sessionStorage` 同步）。
- **`store/composerTaskStore.ts`**：跨页展示「进行中编排/任务」等客户端状态（与全局横幅等配合）。

服务端状态以 TanStack Query 为主；全局 Store 保持精简。

#### 3.8 类型定义

各域类型集中在 **`types/`**（如 `task.ts`、`session.ts`）；与 OpenAPI / `TECH_DESIGN.md` 可追溯枚举对齐，例如：

```
TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
EventModule = 'planning' | 'memory' | 'tool' | 'execution' | 'workflow'
EventKind   = 'plan_created' | 'node_update' | 'step_start' | 'step_end' | 'tool_call' | 'tool_result' | 'llm_stream_delta' | 'error' | 'replan' | ...
MessageRole = 'user' | 'assistant' | 'system'
ToolSource  = 'builtin' | 'mcp' | 'skill'
```

### 4. 前端关键数据流

```
用户在 ChatPage（或含表单的页面）提交任务
  → hooks/useSession 获取 session_id
  → api/tasks.ts createTask（body 以 OpenAPI 为准）
  → 后端返回 task_id 与事件流路径
  → 可导航到 /tasks/:taskId 或通过时间线 Hook 订阅

TaskDetailPage 挂载
  → useTaskDetail(taskId) → 渲染计划（如 TaskPlanSteps）
  → useTaskTimeline(taskId) → REST 已有事件 + api/sse.ts 打开 SSE
      → utils/ 中流式/事件解析工具折叠增量、思考/作答拆分
      → TaskTimeline / TaskEventRow 按 seq 更新
  → 任务终态后 SSE 结束 → useTaskDetail refetch 最终状态
```

---

## 三、架构设计要点

### 1. 前后端对齐策略

| 要点 | 做法 |
|------|------|
| 类型一致性 | 以后端 Pydantic + **`/openapi.json`** 为契约来源；前端 `src/types` 与之对齐（可选用代码生成） |
| 枚举同步 | `TaskStatus`、`EventModule`、`EventKind` 等在 OpenAPI Schema 与 `TECH_DESIGN.md` 中可追溯；前端用字面量联合类型对齐 |
| 错误格式 | 统一 `{ detail, code? }`；`api/client.ts` 统一解析 |

### 2. SSE 可靠性

```
首屏: GET /events (全量或 after_seq=0)
  ↓
SSE:  GET /events/stream (实时增量)
  ↓ 断线
补拉: GET /events?after_seq=<最后收到的 seq>
  ↓
重连: GET /events/stream
```

- 前端维护已见 `seq`，SSE 与 REST 合并时按 `seq` 去重
- 后端仅依赖 **`task_events` 表** 持久化；`event_stream_service` 从库中增量读出推送，**无单独进程内事件总线**；断线后 `GET …/events?after_seq=` 与 [`conversation-flow.md`](../conversation-flow.md) 所述一致即可补拉

### 3. 安全边界

| 边界 | 实现 |
|------|------|
| 密钥不进前端 | 前端仅使用 `VITE_API_BASE_URL`；LLM/MCP 密钥仅后端环境变量 |
| 设置 API 脱敏 | `settings_service.py` 写入时过滤 `api_key`/`secret` 等字段；读取时不返回已标记敏感的 key |
| 日志与 payload | 避免在日志或错误信息中输出完整密钥；`task_events.payload_json` 落库前可按团队规范对敏感键脱敏（当前无独立 `core/security` 模块时，在写入路径集中处理即可） |
| CORS | `main.py` 限制 `CORS_ORIGINS`，仅允许配置的前端域名 |

### 4. 可扩展性预留

| 方向 | 当前 MVP | 扩展路径 |
|------|----------|----------|
| 多 Agent | 单 Agent 单图 | `modules/workflow` 侧新增编译图或子图 + 服务层选型由 `task_id` / 路由区分 |
| 长期记忆 | 会话级 `messages` 表 | 新增向量存储 Repository + `modules/memory` 扩展 |
| OpenTelemetry | 结构化事件日志 | `app/core/` 新增 OTel exporter，与 `task_events` 或日志管线关联 |
| 评测 | 手工验收 | 可选新增 `tests/` 下自动化或 eval 套件 + trace 回放 |
| 数据库迁移 | `create_all` | 启用 `alembic/` 目录 |

---

## 四、与迭代阶段的对照（参考）

以下为**自洽于本仓库当前布局**的模块对照，便于分阶段评审；若团队另有「开发顺序」文档，可与之并列使用。

| 阶段 | 涉及的架构模块（现行路径） |
|------|----------------------------|
| **0** 环境基线 | `app/main.py`（含 `GET /health`）、`app/core/config.py` |
| **1** 数据层 | `app/core/database.py`、`app/shared/*`（ORM 列类型等）、`app/models/*`、`app/repositories/*` |
| **2** HTTP API | `app/schemas/*`、`app/api/v1/*`、`app/services/*`、`app/core/deps.py`、`app/core/exceptions.py` |
| **3** 工具注册表 + MCP | `app/modules/tools/*` |
| **4** Agent 运行时 | `app/modules/workflow/*`、`app/modules/planning/*`、`app/modules/execution/*` |
| **5** SSE | `app/api/v1/tasks.py`（流式端点）、`app/services/event_stream_service.py`、`app/repositories/event_repository.py` |
| **6** 前端壳 | `src/router/index.tsx`、`src/App.tsx`、`src/layouts/*`、`src/api/client.ts`、`src/plugins/*` |
| **7** 前端业务闭环 | `src/views`、`src/api`（含 `sse.ts`）、`src/hooks`、`src/components`、`src/store`、`src/types` |
| **8** 质量与验收 | 手工回归清单 + **`/openapi.json`** 与前端类型联调；详见 [`docs/README.md`](../README.md) 索引 |

---

*文档版本：MVP 架构设计；与 [`TECH_DESIGN.md`](./TECH_DESIGN.md)、[`docs/README.md`](../README.md) 及 OpenAPI 契约对齐。多 Agent 编排、完整 OTel、长期记忆治理等不在本文档默认路径内。*
