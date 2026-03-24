# ForgeAgent 技术设计文档

本文档依据 `docs/PRD.md` 的 MVP 边界与 `docs/RESEARCH.md` 的架构建议编写，与「单 Agent + Plan-and-Execute + 会话记忆 + 工具/MCP 注册表 + 可观测执行」一致。

---

## 1. 技术栈选型


| 部分            | 推荐方案                                                                                                                                                                                    | 理由                                                                                                |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **前端框架**      | **React 18 + TypeScript + Vite+ Tailwind css**；路由用 **React Router**；状态以 **TanStack Query**（服务端任务/事件拉取）+ 轻量 **Zustand** 或组件内 state（避免过度全局化）                                              | 与偏好一致；生态成熟、类型友好；Vite 开发体验好；监控类页面以列表/时间线为主，无需重型状态机库。                                               |
| **后端框架**      | **Python 3.11+ + FastAPI**                                                                                                                                                              | 与偏好一致；异步与 SSE/WebSocket 友好（事件流）；OpenAPI 自动生成便于前后端对齐；与 LangChain/LangGraph 同栈。                     |
| **Agent 运行时** | **LangGraph**（主）+ **LangChain**（模型、工具、MCP 适配）                                                                                                                                           | PRD 要求显式规划循环与可追溯状态；LangGraph 提供图/检查点叙事，与调研「执行层用成熟抽象、避免隐式全局状态」一致；MVP 单 Agent 可用单图或线性节点简化，不必上全量多分支。 |
| **数据库**       | **SQLite**（SQLAlchemy 2.0 async）                                                                                                                                                        | PRD 倾向本地/小团队单机持久化；零运维、文件级备份简单；任务与事件为结构化行存，无需向量库为默认。会话记忆以「会话 ID + 消息/事件表」表达；跨会话长期记忆不在 MVP。         |
| **API 风格**    | **REST** 为主（资源：任务、会话、配置）；**SSE**（`text/event-stream`）用于单任务执行过程的事件流                                                                                                                      | 监控页需实时或准实时更新；SSE 比轮询简单且满足「事件时间线」；后续可并行加 WebSocket 若需双向。                                           |
| **部署方案**      | **前端**：**Vercel** 构建静态资源与环境变量注入（仅公开 `VITE_*` 等非密钥）。**后端**：**不自托管在 Vercel**（Python 长连接/SSE 更适合独立进程）；可选 **Fly.io / Railway / 本机 Docker** 与 SQLite 卷挂载，或小团队 **单机 `docker compose`** 前后端同机。 | 与「前端 Vercel」偏好一致且符合密钥不进前端的 PRD；SQLite 需持久卷，云部署时选支持 volume 的平台或本地优先。                               |


**不确定点（选项与利弊）**


| 议题            | 选项 A                                                       | 选项 B                                     |
| ------------- | ---------------------------------------------------------- | ---------------------------------------- |
| LangGraph 复杂度 | 最小子图：Planner 节点 → Executor 节点 → 条件重规划                      | 完全手写循环 + 仅 LangChain Tools；更轻但状态与回放需更多自研 |
| MCP 接入        | 官方 `langchain-mcp-adapters` 或 MCP Python SDK 拉工具列表后写入统一注册表 | 先 mock 一种 MCP，再换真实 Server；降低首周联调风险       |


**建议**：MVP 选 **LangGraph 最小图 + 一种真实 MCP**（或文档化 mock），与 PRD「至少一种 MCP 或等价模拟」对齐。

---

## 2. 项目结构

推荐 **前后端分目录**（单仓库 monorepo），避免前端误打包后端密钥。**Node/npm 仅用于 `frontend/`**（仓库根目录不设 `package.json`，与 Python 后端解耦，详见 [`README.md`](../README.md)、[`START.md`](../START.md)）。

```
ForgeAgent/
├── README.md
├── START.md
├── AGENTS.md
├── .env.example
├── .gitignore
├── frontend/                 # React + Vite + TypeScript + Tailwind；依赖见 frontend/package.json
├── backend/                  # FastAPI；依赖见 backend/pyproject.toml，包名 forgeagent_backend
├── docs/
│   ├── PRD.md
│   ├── RESEARCH.md
│   └── TECH_DESIGN.md
├── M-prompts/                # 可选：生成各文档的提示词模板
└── LICENSE
```

---

## 3. 数据模型

MVP 使用 SQLite，以下为逻辑模型（表名可 snake_case）。

### 3.1 `tasks`（任务）


| 字段名           | 类型          | 说明                                                         | 必填     |
| ------------- | ----------- | ---------------------------------------------------------- | ------ |
| id            | TEXT (UUID) | 主键                                                         | 是      |
| session_id    | TEXT        | 所属会话/线程                                                    | 是      |
| status        | TEXT        | `pending` / `running` / `success` / `failed` / `cancelled` | 是      |
| summary       | TEXT        | 列表与卡片展示用摘要                                                 | 否      |
| plan_version  | INTEGER     | 当前计划版本（重规划递增）                                              | 是，默认 1 |
| created_at    | DATETIME    | 创建时间                                                       | 是      |
| updated_at    | DATETIME    | 最后更新时间                                                     | 是      |
| error_message | TEXT        | 失败时简短说明                                                    | 否      |


### 3.2 `task_events`（可观测事件流）


| 字段名          | 类型       | 说明                                                             | 必填  |
| ------------ | -------- | -------------------------------------------------------------- | --- |
| id           | INTEGER  | 自增主键                                                           | 是   |
| task_id      | TEXT     | 外键 → tasks.id                                                  | 是   |
| seq          | INTEGER  | 同一任务内顺序号                                                       | 是   |
| ts           | DATETIME | 事件时间                                                           | 是   |
| module       | TEXT     | `planning` / `memory` / `tool` / `execution`（与 PRD 四模块对齐）      | 是   |
| kind         | TEXT     | 如 `plan_created`, `step_start`, `tool_call`, `error`, `replan` | 是   |
| payload_json | TEXT     | JSON：步骤索引、工具名、输入输出摘要、错误栈摘要等                                    | 否   |


索引建议：`task_id + seq`；列表页按 `created_at` 查 `tasks`。

### 3.3 `sessions`（会话）


| 字段名        | 类型          | 说明     | 必填  |
| ---------- | ----------- | ------ | --- |
| id         | TEXT (UUID) | 主键     | 是   |
| title      | TEXT        | 可选展示标题 | 否   |
| created_at | DATETIME    | 是      | 是   |


### 3.4 `messages`（会话内消息，记忆）


| 字段名        | 类型       | 说明                              | 必填  |
| ---------- | -------- | ------------------------------- | --- |
| id         | INTEGER  | 自增                              | 是   |
| session_id | TEXT     | 外键                              | 是   |
| role       | TEXT     | `user` / `assistant` / `system` | 是   |
| content    | TEXT     | 正文                              | 是   |
| created_at | DATETIME | 是                               | 是   |


### 3.5 `settings_kv`（非密钥配置）


| 字段名        | 类型       | 说明                                      | 必填  |
| ---------- | -------- | --------------------------------------- | --- |
| key        | TEXT     | 主键，如 `mcp_servers_json`, `skills_paths` | 是   |
| value_json | TEXT     | JSON 字符串                                | 是   |
| updated_at | DATETIME | 是                                       | 是   |


**说明**：LLM/API Key、MCP 密钥仅存环境变量或服务端保密存储，**不**入此表明文；表中可存「连接名、URL、是否启用」等非敏感元数据。

### 3.6 `skills_manifest`（可选，便于列表展示）

若 Skills 仅从文件系统扫描，可运行时生成不持久化；若需「已加载 Skill 列表」可缓存：


| 字段名         | 类型       | 说明       | 必填  |
| ----------- | -------- | -------- | --- |
| name        | TEXT     | Skill 标识 | 是   |
| source_path | TEXT     | 路径       | 是   |
| loaded_at   | DATETIME | 是        | 是   |


---

## 4. API 接口设计

基础路径示例：`/api/v1`。认证：MVP 可省略或单 API Token 头（后续再接用户表）。

### 4.1 任务


| 接口名称    | 方法     | 请求参数                                                       | 返回格式                                                                                                         |
| ------- | ------ | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 创建并启动任务 | `POST` | Body: `{ "session_id": "uuid", "user_message": "string" }` | `{ "task_id": "uuid", "stream_url": "/api/v1/tasks/{id}/events" }`                                           |
| 任务列表    | `GET`  | Query: `limit`, `offset`, `status?`                        | `{ "items": [ { "id", "status", "summary", "created_at", ... } ], "total": n }`                              |
| 任务详情    | `GET`  | Path: `task_id`                                            | `{ "id", "session_id", "status", "summary", "plan_version", "plan": { "steps": [...] }, "created_at", ... }` |
| 任务事件历史  | `GET`  | Path: `task_id`；Query: `after_seq?`                        | `{ "events": [ { "seq", "ts", "module", "kind", "payload" } ] }`                                             |


### 4.2 实时事件流（SSE）


| 接口名称   | 方法    | 请求参数                                                | 返回格式                                                     |
| ------ | ----- | --------------------------------------------------- | -------------------------------------------------------- |
| 订阅任务事件 | `GET` | Path: `task_id`；Header: `Accept: text/event-stream` | SSE：`event: step\ndata: {...}\n\n`（与 `task_events` 一致结构） |


### 4.3 会话


| 接口名称   | 方法     | 请求参数                           | 返回格式                       |
| ------ | ------ | ------------------------------ | -------------------------- |
| 创建会话   | `POST` | Body: `{ "title?": "string" }` | `{ "session_id": "uuid" }` |
| 会话消息列表 | `GET`  | Path: `session_id`             | `{ "messages": [ ... ] }`  |


### 4.4 设置


| 接口名称 | 方法    | 请求参数             | 返回格式                                          |
| ---- | ----- | ---------------- | --------------------------------------------- |
| 获取设置 | `GET` | —                | `{ "mcp": [...], "skills_paths": [...] }`（脱敏） |
| 更新设置 | `PUT` | Body: 同上（不含密钥字段） | `{ "ok": true }`                              |


### 4.5 工具注册表（只读）


| 接口名称 | 方法    | 请求参数 | 返回格式                                                       |
| ---- | ----- | ---- | ---------------------------------------------------------- |
| 列出工具 | `GET` | —    | `{ "tools": [ { "name", "description", "source": "builtin" |


### 4.6 健康检查


| 接口名称 | 方法              | 请求参数 | 返回格式                 |
| ---- | --------------- | ---- | -------------------- |
| 健康   | `GET` `/health` | —    | `{ "status": "ok" }` |


---

## 5. 关键技术点

### 5.1 Plan-and-Execute 与重规划边界

- **难点**：在「失败 / 信息不足」时触发重规划，需避免无限循环并保留计划版本可追溯。
- **方案**：LangGraph 中用条件边返回 `planner`；配置 `max_replan_attempts` 与超时；每次重规划 `plan_version++` 并写 `task_events`（`kind=replan`）。

### 5.2 MCP 与 Skills 统一注册表

- **难点**：两种来源不能两套调用心智。
- **方案**：启动时与按需刷新：MCP 工具拉取后映射为与内置工具相同的元数据结构（name、description、source=mcp）；Skills 按目录解析为额外工具或提示模板，**展示与权限检查走同一 `ToolRegistry`**。

### 5.3 可观测与性能（列表 ≤2s、详情 ≤1s）

- **难点**：事件量大时前端渲染与单次查询变慢。
- **方案**：列表分页 + 仅摘要字段；详情页事件 `after_seq` 增量加载；超大 `payload` 截断存储与 UI 默认折叠全文；后端对密钥字段脱敏。

### 5.4 密钥与安全

- **难点**：Vercel 前端与开源仓库不能泄露密钥。
- **方案**：所有 LLM/MCP 密钥仅 `api` 进程环境变量；前端 `VITE_API_BASE_URL` 等无密钥；日志序列化前对已知键名打码。

### 5.5 部署形态分裂（前端 Vercel + 后端独立）

- **难点**：跨域与 SSE、Cookie/Token。
- **方案**：FastAPI 配置 CORS 允许 Vercel 域名；SSE 使用 `fetch` + `ReadableStream` 或 `EventSource`（注意浏览器对自定义 header 限制，Token 可放 query 仅在内网或配合短效 token，MVP 同机可免鉴权）。

---

## 6. 开发环境

### 6.1 Node.js

- **版本**：**20 LTS** 或 **22 LTS**（与 Vite 5/6 及 React 18 兼容；以项目 `engines` 锁死）。

### 6.2 Python

- **版本**：**3.11+**（建议 3.12），与 LangChain/LangGraph 官方支持矩阵一致。 使用虚拟环境管理包

### 6.3 全局/常用工具（可选全局，推荐项目内）


| 工具                    | 用途               |
| --------------------- | ---------------- |
| `pnpm` 或 `npm`        | 前端包管理            |
| `uv` 或 `pip` + `venv` | Python 依赖与虚拟环境   |
| `sqlite3` CLI         | 本地调试库文件          |
| Docker Desktop        | 可选：compose 一键起后端 |


### 6.4 环境变量清单（后端 `apps/api` 示例）


| 变量名                     | 说明                                                    |
| ----------------------- | ----------------------------------------------------- |
| `DATABASE_URL`          | 默认 `sqlite+aiosqlite:///./data/forgeagent.db`         |
| `LLM_API_KEY` / 具体厂商变量名 | 按所选模型提供商二选一或统一封装                                      |
| `MCP`_*                 | 各 MCP Server 所需（若不用环境变量则可仅存非敏感连接信息在 DB，密钥仍走 env）      |
| `CORS_ORIGINS`          | 前端源，如 `http://localhost:5173`, `https://*.vercel.app` |
| `LOG_LEVEL`             | `INFO` / `DEBUG`                                      |


前端（Vite）示例：


| 变量名                 | 说明                      |
| ------------------- | ----------------------- |
| `VITE_API_BASE_URL` | 后端 API 根 URL，**不含**任何密钥 |


---

*文档版本与 PRD MVP 对齐；多 Agent、完整 OTel、向量长期记忆等为后续里程碑，不在此设计默认路径内。*