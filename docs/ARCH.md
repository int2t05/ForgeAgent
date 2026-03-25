# ForgeAgent 全栈架构设计（MVP）

本文档定义 ForgeAgent 前后端**目录结构与模块职责**；与 [`PRD.md`](PRD.md) MVP 边界、[`TECH_DESIGN.md`](TECH_DESIGN.md) 数据模型、[`API.md`](API.md) 契约、[`DEVELOP_ORDER.md`](DEVELOP_ORDER.md) 阶段顺序一致。**不含可运行代码。**

---

## 一、后端架构

### 1. 分层设计思想

后端采用 **四层架构**，自上而下职责递减、依赖单向：

```
HTTP 层（api/）→ 服务层（services/）→ 仓储层（repositories/）→ 模型层（models/）
                     ↕
              Agent 运行时（agent/）⟷ 工具注册表（tools/）
```

| 层级 | 职责 | 规则 |
|------|------|------|
| **API 层** | 路由定义、请求校验、响应序列化、SSE 推送 | 仅调用 Service；禁止直接操作 DB Session |
| **服务层** | 业务编排、状态流转、事务边界 | 可调用多个 Repository；可触发 Agent 执行 |
| **仓储层** | 单表 CRUD 与查询封装 | 仅操作 SQLAlchemy AsyncSession；不含业务判断 |
| **模型层** | ORM 声明式模型 + Pydantic Schema | ORM 与 Schema 分离，互不依赖 |
| **Agent 运行时** | LangGraph 图定义、节点、执行器 | 通过 Service 写 DB；通过 ToolRegistry 调用工具 |
| **工具注册表** | 内置/MCP/Skill 工具统一注册 | 提供标准接口供 Agent 节点消费 |

### 2. 后端文件结构

```
backend/
├── pyproject.toml                          # 项目元数据、依赖声明（Hatch 构建）
├── alembic.ini                             # 数据库迁移配置（可选，MVP 可用 create_all）
├── alembic/                                # 迁移脚本目录（可选）
│   ├── env.py
│   └── versions/
│
├── app/                                    # 主应用包
│   ├── __init__.py
│   ├── main.py                             # FastAPI 工厂：lifespan、中间件挂载、路由注册
│   ├── config.py                           # pydantic-settings：读取环境变量，统一配置入口
│   ├── database.py                         # AsyncEngine / async_sessionmaker / 建表
│   │
│   ├── models/                             # SQLAlchemy ORM 声明式模型
│   │   ├── __init__.py                     # 统一导出 Base 及所有 Model
│   │   ├── base.py                         # DeclarativeBase + 公共 mixin（id、时间戳）
│   │   ├── task.py                         # Task 模型（对应 tasks 表）
│   │   ├── task_event.py                   # TaskEvent 模型（对应 task_events 表）
│   │   ├── session.py                      # Session 模型（对应 sessions 表）
│   │   ├── message.py                      # Message 模型（对应 messages 表）
│   │   └── setting.py                      # SettingKV 模型（对应 settings_kv 表）
│   │
│   ├── schemas/                            # Pydantic v2 请求/响应 Schema
│   │   ├── __init__.py
│   │   ├── common.py                       # ErrorResponse、PaginatedResponse 等通用结构
│   │   ├── task.py                         # TaskCreate、TaskResponse、TaskListResponse
│   │   ├── event.py                        # EventResponse、EventListResponse
│   │   ├── session.py                      # SessionCreate、SessionResponse
│   │   ├── message.py                      # MessageResponse
│   │   ├── setting.py                      # SettingsResponse、SettingsUpdate
│   │   └── tool.py                         # ToolInfo、ToolListResponse
│   │
│   ├── api/                                # HTTP 路由层
│   │   ├── __init__.py
│   │   ├── deps.py                         # FastAPI 依赖注入：get_db_session、get_settings 等
│   │   ├── health.py                       # GET /health 健康检查路由
│   │   └── v1/                             # /api/v1 版本化路由组
│   │       ├── __init__.py
│   │       ├── router.py                   # 聚合 v1 所有子路由的 APIRouter
│   │       ├── tasks.py                    # 任务相关：POST 创建、GET 列表/详情/事件/SSE
│   │       ├── sessions.py                 # 会话：POST 创建、GET 消息列表
│   │       ├── settings.py                 # 设置：GET 获取、PUT 更新
│   │       └── tools.py                    # 工具注册表：GET 列表
│   │
│   ├── services/                           # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── task_service.py                 # 任务创建、状态流转、触发 Agent、查询
│   │   ├── event_service.py                # 事件追加（原子 seq 递增）、增量查询、SSE 订阅
│   │   ├── session_service.py              # 会话创建与查询
│   │   ├── message_service.py              # 消息写入与分页读取
│   │   ├── setting_service.py              # KV 配置读写（脱敏策略）
│   │   └── tool_service.py                 # 从 ToolRegistry 查询已注册工具
│   │
│   ├── repositories/                       # 数据访问层（Repository Pattern）
│   │   ├── __init__.py
│   │   ├── task_repo.py                    # tasks 表增删改查
│   │   ├── event_repo.py                   # task_events 表写入与 after_seq 查询
│   │   ├── session_repo.py                 # sessions 表操作
│   │   ├── message_repo.py                 # messages 表操作
│   │   └── setting_repo.py                 # settings_kv 表操作
│   │
│   ├── agent/                              # Agent 运行时（LangGraph + LangChain）
│   │   ├── __init__.py
│   │   ├── state.py                        # AgentState TypedDict（图的共享状态结构）
│   │   ├── graph.py                        # LangGraph 图定义：节点注册、条件边、编译
│   │   ├── nodes/                          # 图节点实现
│   │   │   ├── __init__.py
│   │   │   ├── planner.py                  # 规划节点：调用 LLM 生成/更新执行计划
│   │   │   └── executor.py                 # 执行节点：按步骤调用工具并写回事件
│   │   ├── prompts.py                      # 提示词模板（规划、执行、重规划等）
│   │   └── runner.py                       # run_agent() 入口：任务生命周期管理
│   │
│   ├── tools/                              # 统一工具注册表
│   │   ├── __init__.py
│   │   ├── registry.py                     # ToolRegistry 类：注册、查询、刷新
│   │   ├── base.py                         # 工具元数据结构（name、description、source、权限）
│   │   ├── builtin/                        # 内置工具
│   │   │   ├── __init__.py
│   │   │   └── example_tool.py             # 示例内置工具（MVP 至少一个）
│   │   ├── mcp/                            # MCP 适配层
│   │   │   ├── __init__.py
│   │   │   └── adapter.py                  # MCP Client → 统一工具接口映射
│   │   └── skills/                         # Skills 加载器
│   │       ├── __init__.py
│   │       └── loader.py                   # 扫描约定目录 → 注册为工具/模板
│   │
│   └── core/                               # 横切基础设施
│       ├── __init__.py
│       ├── events.py                       # 内存事件总线（SSE pub/sub）
│       ├── security.py                     # 日志脱敏、密钥字段过滤
│       └── exceptions.py                   # 自定义异常（业务错误码映射 HTTP 状态）
│
├── skills/                                 # Skills 约定目录（示例）
│   └── example_skill/
│       ├── manifest.json                   # Skill 元数据：名称、描述、工具声明
│       └── prompts/                        # Skill 附带的提示词模板
│
├── tests/                                  # 测试目录
│   ├── conftest.py                         # pytest fixtures（测试 DB、测试客户端）
│   ├── test_api/                           # API 层集成测试
│   │   ├── test_health.py
│   │   ├── test_tasks.py
│   │   └── test_sessions.py
│   ├── test_services/                      # Service 层单元测试
│   │   ├── test_task_service.py
│   │   └── test_event_service.py
│   └── test_agent/                         # Agent 运行时测试
│       └── test_graph.py
│
└── data/                                   # SQLite 数据文件（.gitignore）
    └── .gitkeep
```

### 3. 后端各模块详细说明

#### 3.1 `app/main.py` — 应用入口

- 创建 FastAPI 实例，配置 `title`、`version`
- 定义 `lifespan` 异步上下文管理器：启动时初始化数据库（`create_all` 或 Alembic）、加载工具注册表；关闭时释放连接
- 挂载 CORS 中间件（`CORS_ORIGINS` 环境变量控制）
- 注册 `/health` 路由与 `/api/v1` 路由组

#### 3.2 `app/config.py` — 配置中心

- 使用 `pydantic-settings` 的 `BaseSettings` 读取环境变量
- 统一管理：`DATABASE_URL`、`LLM_API_KEY`、`CORS_ORIGINS`、`LOG_LEVEL`、`MAX_REPLAN_ATTEMPTS` 等
- 提供单例访问，通过 FastAPI 依赖注入分发

#### 3.3 `app/database.py` — 数据库引擎

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
| `session.py` | `sessions` | `id(UUID)`、`title`、`created_at` |
| `message.py` | `messages` | `id(自增)`、`session_id(FK)`、`role`、`content`、`created_at` |
| `setting.py` | `settings_kv` | `key(PK)`、`value_json`、`updated_at` |

索引策略：`task_events` 上建 `(task_id, seq)` 联合唯一索引。

#### 3.5 `app/schemas/` — Pydantic Schema

与 [`API.md`](API.md) 请求/响应格式严格对齐：

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
| `health.py` | `/` | `GET /health` |
| `v1/tasks.py` | `/api/v1/tasks` | `POST` 创建任务、`GET` 列表、`GET /{task_id}` 详情、`GET /{task_id}/events` 事件历史、`GET /{task_id}/events/stream` SSE |
| `v1/sessions.py` | `/api/v1/sessions` | `POST` 创建会话、`GET /{session_id}/messages` 消息列表 |
| `v1/settings.py` | `/api/v1/settings` | `GET` 获取、`PUT` 更新 |
| `v1/tools.py` | `/api/v1/tools` | `GET` 工具注册表 |
| `v1/router.py` | `/api/v1` | 聚合上述子路由 |
| `deps.py` | — | `get_db()` 注入 AsyncSession、`get_settings()` 注入配置 |

#### 3.7 `app/services/` — 业务逻辑层

| 文件 | 核心职责 |
|------|----------|
| `task_service.py` | 创建任务（写 tasks + messages）→ 触发 `runner.run_agent()` 后台执行；任务列表分页查询；状态流转校验（如 `running → success/failed`） |
| `event_service.py` | `append_event()`：原子递增 seq 写入 task_events；`get_events(after_seq)`：增量查询；`subscribe(task_id)`：SSE 订阅（结合内存事件总线） |
| `session_service.py` | 会话创建与查询 |
| `message_service.py` | 消息写入（user/assistant/system）、按 session_id 分页读取 |
| `setting_service.py` | KV 配置读写；写入时过滤禁止的密钥字段 |
| `tool_service.py` | 从 `ToolRegistry` 实例获取已注册工具列表 |

#### 3.8 `app/repositories/` — 数据访问层

每个 Repository 封装对应表的数据库操作：

- 接收 `AsyncSession` 作为参数
- 仅包含数据读写逻辑，不含业务判断
- 提供类型安全的返回值（ORM Model 实例或标量）
- 查询方法支持分页参数（`limit`、`offset`）

#### 3.9 `app/agent/` — Agent 运行时

| 文件 | 职责 |
|------|------|
| `state.py` | 定义 `AgentState(TypedDict)`：`messages`、`plan`、`current_step`、`replan_count`、`task_id` 等；使用 `Annotated` 配合 LangGraph 的消息合并 |
| `graph.py` | 构建 LangGraph `StateGraph`：注册 `planner`、`executor` 节点；定义条件边（执行完成 → END / 需要重规划 → planner）；编译为可执行图 |
| `nodes/planner.py` | 规划节点：调用 LLM 生成结构化步骤计划；重规划时分析失败原因并更新计划；写 `plan_created` / `replan` 事件 |
| `nodes/executor.py` | 执行节点：按计划步骤逐个执行；调用 ToolRegistry 中的工具；写 `step_start` / `tool_call` / `tool_result` / `error` 事件 |
| `prompts.py` | 提示词模板集中管理：规划模板、执行模板、重规划模板 |
| `runner.py` | `run_agent(task_id)` 入口：从 DB 加载任务上下文 → 构建图 → 执行 → 写终态（`success`/`failed`）；异常兜底与日志脱敏 |

**LangGraph 最小图结构**：

```
[START] → planner → executor → should_replan?
                                  ├─ yes (replan_count < max) → planner
                                  └─ no → [END]
```

#### 3.10 `app/tools/` — 统一工具注册表

| 文件 | 职责 |
|------|------|
| `base.py` | 工具元数据协议：`ToolMeta(name, description, source, read_only)`；`BaseTool` 抽象基类 |
| `registry.py` | `ToolRegistry` 单例：`register()`、`get_all()`、`get_by_name()`、`refresh()`；启动时加载，按需刷新 |
| `builtin/example_tool.py` | MVP 内置示例工具（如搜索或计算器），验证注册与调用链路 |
| `mcp/adapter.py` | MCP Client 适配器：连接 MCP Server → 拉取工具列表 → 映射为 `ToolMeta(source="mcp")` 注册入 Registry |
| `skills/loader.py` | 扫描 `skills/` 约定目录下的 `manifest.json` → 解析声明 → 注册为 `ToolMeta(source="skill")` |

**三类工具统一注册、统一消费**，Agent 节点只面向 `ToolRegistry` 接口，无需区分来源。

#### 3.11 `app/core/` — 横切基础设施

| 文件 | 职责 |
|------|------|
| `events.py` | 内存级事件总线（`asyncio.Queue` 或类似结构）；`publish(task_id, event)` / `subscribe(task_id)` 支撑 SSE 实时推送 |
| `security.py` | `sanitize_payload()`：序列化前对 `api_key`、`token` 等已知键名打码；`is_sensitive_key()`：设置 API 写入前过滤 |
| `exceptions.py` | `AppError` 基类及子类（`NotFoundError`、`ConflictError`、`ValidationError`）；配合 FastAPI exception_handler 映射到 HTTP 状态码 + [`API.md`](API.md) §1.1 错误格式 |

### 4. 后端关键数据流

```
用户请求 POST /api/v1/tasks
  → api/v1/tasks.py (校验 Schema)
    → services/task_service.py (创建 Task + Message)
      → repositories/task_repo.py (写 tasks 表)
      → repositories/message_repo.py (写 messages 表)
    → agent/runner.py (asyncio.create_task 后台启动)
      → agent/graph.py (编译图并执行)
        → agent/nodes/planner.py (LLM → 生成 plan)
          → services/event_service.py (写 plan_created 事件)
        → agent/nodes/executor.py (逐步执行)
          → tools/registry.py (获取并调用工具)
          → services/event_service.py (写 step/tool/error 事件)
            → core/events.py (publish → SSE 推送)
      → services/task_service.py (更新终态 success/failed)
  ← 返回 { task_id, events_stream_path }
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

```
frontend/
├── index.html                              # Vite HTML 入口
├── package.json                            # 依赖与脚本（npm 仅在此目录执行）
├── package-lock.json
├── vite.config.ts                          # Vite + React + Tailwind 插件配置
├── tsconfig.json                           # TypeScript 项目引用
├── tsconfig.app.json                       # 应用 TS 编译配置
├── tsconfig.node.json                      # Node/Vite 配置文件 TS 编译
├── eslint.config.js                        # ESLint flat config
├── .prettierrc.json                        # Prettier 格式化规则
├── .prettierignore
│
├── public/                                 # 静态资源（不经 Vite 处理）
│   ├── favicon.svg
│   └── icons.svg
│
└── src/
    ├── main.tsx                            # React 入口：挂载 App 到 DOM
    ├── App.tsx                             # 根组件：QueryClientProvider + RouterProvider
    ├── index.css                           # Tailwind 指令 + CSS 变量（主题色）
    ├── router.tsx                          # React Router 路由表定义
    │
    ├── api/                                # API 请求层（与后端契约对齐）
    │   ├── client.ts                       # fetch/axios 实例：baseURL = VITE_API_BASE_URL
    │   ├── tasks.ts                        # createTask、getTasks、getTask、getTaskEvents
    │   ├── sessions.ts                     # createSession、getSessionMessages
    │   ├── settings.ts                     # getSettings、updateSettings
    │   ├── tools.ts                        # getTools
    │   └── sse.ts                          # SSE 客户端封装：连接、重连、after_seq 补拉
    │
    ├── hooks/                              # 自定义 React Hooks
    │   ├── useTasks.ts                     # 任务列表 TanStack Query（分页、筛选）
    │   ├── useTaskDetail.ts                # 单任务详情 Query
    │   ├── useTaskEvents.ts                # SSE + REST 增量合并：按 seq 排序、去重
    │   ├── useSession.ts                   # 会话管理：自动创建 / sessionStorage 缓存
    │   ├── useSettings.ts                  # 设置 Query + Mutation
    │   └── useTools.ts                     # 工具列表 Query
    │
    ├── pages/                              # 路由级页面组件
    │   ├── HomePage.tsx                    # / — 仪表盘：最近任务 + 发起任务表单
    │   ├── TaskListPage.tsx                # /tasks — 全部任务列表（分页、状态筛选）
    │   ├── TaskDetailPage.tsx              # /tasks/:taskId — 计划 + 时间线 + 错误区
    │   ├── SettingsPage.tsx                # /settings — MCP/Skills 配置表单
    │   ├── AboutPage.tsx                   # /about — MVP 边界说明、帮助信息
    │   └── NotFoundPage.tsx                # 404 页面
    │
    ├── components/                         # 可复用 UI 组件
    │   ├── layout/                         # 布局壳组件
    │   │   ├── AppLayout.tsx               # 整体布局：侧边栏 + 主内容区
    │   │   ├── Sidebar.tsx                 # 侧边导航：首页、任务、设置、关于
    │   │   └── Header.tsx                  # 顶栏：产品名、面包屑（可选）
    │   │
    │   ├── task/                           # 任务相关组件
    │   │   ├── TaskCard.tsx                # 列表项卡片：状态、摘要、时间
    │   │   ├── TaskStatusBadge.tsx         # 状态标签：running/success/failed 颜色映射
    │   │   ├── TaskCreateForm.tsx          # 任务创建表单：多行文本输入 + 提交
    │   │   ├── PlanView.tsx                # 计划步骤展示：步骤列表 + 版本号
    │   │   ├── EventTimeline.tsx           # 执行时间线容器：按 seq 排列事件
    │   │   └── EventItem.tsx              # 单条事件：模块标签、kind 图标、摘要/展开
    │   │
    │   ├── settings/                       # 设置相关组件
    │   │   ├── McpConfigPanel.tsx          # MCP 连接配置面板（非密钥）
    │   │   └── SkillsConfigPanel.tsx       # Skills 路径/启用开关面板
    │   │
    │   └── common/                         # 通用基础组件
    │       ├── LoadingSpinner.tsx          # 加载动画
    │       ├── ErrorAlert.tsx              # 错误提示（可关闭）
    │       ├── EmptyState.tsx              # 空状态占位
    │       ├── ConfirmDialog.tsx           # 二次确认弹窗（重新执行等操作）
    │       ├── Pagination.tsx             # 分页控件
    │       ├── CollapsibleSection.tsx      # 可展开/折叠区块
    │       └── CodeBlock.tsx              # 等宽字体 JSON/日志查看器
    │
    ├── stores/                             # Zustand 状态管理
    │   └── sessionStore.ts                # 当前 session_id 管理（内存 + sessionStorage）
    │
    ├── types/                              # 共享 TypeScript 类型
    │   ├── task.ts                         # Task、TaskStatus、TaskEvent、EventModule、EventKind
    │   ├── session.ts                      # Session、Message、MessageRole
    │   ├── settings.ts                     # Settings、McpConfig
    │   └── tool.ts                         # ToolInfo、ToolSource
    │
    └── lib/                                # 工具函数
        ├── constants.ts                    # API_BASE_URL、状态颜色映射、分页默认值
        └── format.ts                       # 日期格式化、文本截断、JSON 安全解析
```

### 3. 前端各模块详细说明

#### 3.1 `src/App.tsx` — 根组件

- 包裹 `QueryClientProvider`（TanStack Query）
- 包裹 `RouterProvider`（React Router）
- 全局错误边界

#### 3.2 `src/router.tsx` — 路由配置

| 路由 | 页面组件 | 布局 |
|------|----------|------|
| `/` | `HomePage` | `AppLayout` |
| `/tasks` | `TaskListPage` | `AppLayout` |
| `/tasks/:taskId` | `TaskDetailPage` | `AppLayout` |
| `/settings` | `SettingsPage` | `AppLayout` |
| `/about` | `AboutPage` | `AppLayout` |
| `*` | `NotFoundPage` | `AppLayout` |

所有业务路由共享 `AppLayout`（侧边栏 + 主内容区）。

#### 3.3 `src/api/` — 请求层

| 文件 | 职责 |
|------|------|
| `client.ts` | 创建带 `baseURL` 的 fetch 封装或 axios 实例；统一处理错误响应（解析 `ErrorResponse`） |
| `tasks.ts` | `createTask(body)`、`getTasks(params)`、`getTask(taskId)`、`getTaskEvents(taskId, afterSeq?)` |
| `sessions.ts` | `createSession(body?)`、`getSessionMessages(sessionId, params?)` |
| `settings.ts` | `getSettings()`、`updateSettings(body)` |
| `tools.ts` | `getTools()` |
| `sse.ts` | `subscribeTaskEvents(taskId, onEvent, onError?)`：封装 `EventSource` / `fetch + ReadableStream`；支持 `last_event_id` 断线重连 |

#### 3.4 `src/hooks/` — 数据 Hooks

| 文件 | 核心逻辑 |
|------|----------|
| `useTasks.ts` | `useQuery(['tasks', params])` 分页列表；可选 `refetchInterval` 轮询 |
| `useTaskDetail.ts` | `useQuery(['task', taskId])` 单任务详情 |
| `useTaskEvents.ts` | 首屏 REST 拉全量 → SSE 增量追加；按 `seq` 排序去重；断线后 `afterSeq` 补拉再重连 |
| `useSession.ts` | 检查 `sessionStorage` 是否有 `session_id`；无则自动调用 `createSession`；返回当前 session_id |
| `useSettings.ts` | `useQuery` + `useMutation` 封装设置读写 |
| `useTools.ts` | `useQuery(['tools'])` 工具列表 |

#### 3.5 `src/pages/` — 页面组件

| 页面 | 核心区块 | 数据依赖 |
|------|----------|----------|
| `HomePage` | 产品标题 + 最近任务列表 + 发起任务表单 | `useTasks(limit=5)` + `useSession` |
| `TaskListPage` | 状态筛选 + 任务卡片列表 + 分页 | `useTasks(limit, offset, status?)` |
| `TaskDetailPage` | 顶栏状态 + 计划区 + 执行时间线 + 错误高亮 + 原始日志折叠 | `useTaskDetail` + `useTaskEvents`（SSE） |
| `SettingsPage` | MCP 配置面板 + Skills 配置面板 + 密钥说明 | `useSettings` |
| `AboutPage` | MVP 边界静态说明 | 无必须请求 |

#### 3.6 `src/components/` — 组件分组

按业务域分组（`layout/`、`task/`、`settings/`、`common/`），避免所有组件平铺在一个目录：

- **`layout/`**：应用骨架，页面间共享
- **`task/`**：任务监控核心 UI，仅在任务相关页面使用
- **`settings/`**：设置表单组件
- **`common/`**：通用基础 UI，全站复用

#### 3.7 `src/stores/sessionStore.ts` — 全局状态

仅管理 **当前会话 session_id**：

- 启动时从 `sessionStorage` 恢复
- 无有效值时触发创建
- 值变更时同步写入 `sessionStorage`

MVP 阶段全局状态极轻量，仅此一处使用 Zustand；任务/事件等服务端状态全部由 TanStack Query 管理。

#### 3.8 `src/types/` — 类型定义

与后端 Pydantic Schema 及 [`API.md`](API.md) 枚举一一对应：

```
TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
EventModule = 'planning' | 'memory' | 'tool' | 'execution'
EventKind   = 'plan_created' | 'step_start' | 'tool_call' | 'tool_result' | 'error' | 'replan' | ...
MessageRole = 'user' | 'assistant' | 'system'
ToolSource  = 'builtin' | 'mcp' | 'skill'
```

### 4. 前端关键数据流

```
用户在 HomePage 输入任务描述并提交
  → TaskCreateForm 调用 useSession 获取 session_id
  → api/tasks.ts createTask({ session_id, user_message })
  → 后端返回 { task_id, events_stream_path }
  → React Router 导航到 /tasks/:taskId

TaskDetailPage 挂载
  → useTaskDetail(taskId) 拉取任务详情 → 渲染 PlanView
  → useTaskEvents(taskId) 拉取已有事件 + 打开 SSE 连接
    → api/sse.ts subscribeTaskEvents(taskId, onEvent)
      → 后端 SSE 推送事件
      → 按 seq 排序插入本地事件数组
      → EventTimeline 实时更新渲染
  → 任务终态时 SSE 关闭 → useTaskDetail refetch 最终状态
```

---

## 三、架构设计要点

### 1. 前后端对齐策略

| 要点 | 做法 |
|------|------|
| 类型一致性 | 后端 Pydantic Schema 为单一真相源；前端 `types/` 与之手动对齐（后续可用 OpenAPI Generator 自动生成） |
| 枚举同步 | `TaskStatus`、`EventModule`、`EventKind` 等枚举在 [`API.md`](API.md) §8 定义，前后端各维护一份字面量类型 |
| 错误格式 | 统一 `{ detail, code? }` 结构；前端 `client.ts` 统一拦截并转为类型化错误 |

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

- 前端维护 `maxSeenSeq`，SSE 事件按 `seq` 去重
- 后端 `core/events.py` 事件总线 + `event_repo` 持久化双写，确保断线补拉无数据丢失

### 3. 安全边界

| 边界 | 实现 |
|------|------|
| 密钥不进前端 | 前端仅使用 `VITE_API_BASE_URL`；LLM/MCP 密钥仅后端环境变量 |
| 设置 API 脱敏 | `setting_service.py` 写入时过滤 `api_key`/`secret` 等字段；读取时不返回已标记敏感的 key |
| 日志脱敏 | `core/security.py` 在 `payload_json` 序列化前对已知敏感键打码 |
| CORS | `main.py` 限制 `CORS_ORIGINS`，仅允许配置的前端域名 |

### 4. 可扩展性预留

| 方向 | 当前 MVP | 扩展路径 |
|------|----------|----------|
| 多 Agent | 单 Agent 单图 | `agent/` 下新增图定义 + 路由/编排层 |
| 长期记忆 | 会话级 `messages` 表 | 新增向量存储 Repository + 记忆服务 |
| OpenTelemetry | 结构化事件日志 | `core/` 新增 OTel exporter，事件总线挂 span |
| 评测 | 手工验收 | `tests/` 新增 eval 套件 + trace 回放 |
| 数据库迁移 | `create_all` | 启用 `alembic/` 目录 |

---

## 四、与 DEVELOP_ORDER 阶段对照

| 开发阶段 | 涉及的架构模块 |
|----------|--------------|
| **阶段 0** 环境基线 | `main.py`、`config.py`、`health.py` |
| **阶段 1** 数据层 | `database.py`、`models/*`、`repositories/*` |
| **阶段 2** HTTP API | `schemas/*`、`api/v1/*`、`services/*`、`deps.py`、`exceptions.py` |
| **阶段 3** 工具注册表 + MCP | `tools/*`（registry、builtin、mcp、skills） |
| **阶段 4** Agent 运行时 | `agent/*`（state、graph、nodes、prompts、runner） |
| **阶段 5** SSE | `core/events.py`、`api/v1/tasks.py`(SSE 端点)、`services/event_service.py`(subscribe) |
| **阶段 6** 前端壳 | `router.tsx`、`App.tsx`、`layout/*`、`api/client.ts`、`stores/` |
| **阶段 7** 前端监控闭环 | `pages/*`、`components/task/*`、`hooks/*`、`api/sse.ts` |
| **阶段 8** 质量与验收 | `tests/*` |

---

*文档版本：MVP 架构设计；与 [`PRD.md`](PRD.md)、[`TECH_DESIGN.md`](TECH_DESIGN.md)、[`API.md`](API.md)、[`DEVELOP_ORDER.md`](DEVELOP_ORDER.md) 对齐。多 Agent 编排、完整 OTel、长期记忆治理等不在本文档默认路径内。*
