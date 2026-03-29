# ForgeAgent REST / SSE API 说明（MVP）

本文档与 [`PRD.md`](PRD.md) MVP 边界、[`TECH_DESIGN.md`](TECH_DESIGN.md) 数据模型一致；**仅规划与契约**，实现以 OpenAPI 为准。

---

## 1. 约定

| 项目 | 说明 |
|------|------|
| API 前缀 | 业务资源统一为 `/api/v1`；**健康检查**单独使用根路径 `GET /health`（不设 `/api/v1` 前缀）。 |
| 时间 | 响应中时间字段为 **ISO 8601** 字符串（UTC 或带偏移，实现需前后端一致）。 |
| 分页 | 列表类 Query：`limit`（默认如 20，上限如 100）、`offset`（默认 0）。 |
| 认证 | MVP **可省略**；若启用则为单 Token（如 `Authorization: Bearer <token>`），本表不展开 OAuth。 |
| 内容类型 | JSON 请求/响应：`Content-Type: application/json`；SSE 见 §6。 |
| ID | `task_id`、`session_id` 等为 UUID 字符串（与 `tasks.id`、`sessions.id` 一致）。 |

### 1.1 错误响应（统一形状）

非 2xx 时响应体建议：

```json
{
  "detail": "人类可读说明",
  "code": "可选机器可读代码，如 VALIDATION_ERROR"
}
```

具体 HTTP 状态：`400` 参数错误、`404` 资源不存在、`409` 状态冲突（如对已终态任务重复启动）、`500` 服务器错误。表中「返回格式」列对错误情况可写「见 §1.1」。

---

## 2. 健康检查

| 接口名 | 方法 | 路径 | 描述 | 请求参数 | 返回格式 |
|--------|------|------|------|----------|----------|
| 健康检查 | `GET` | `/health` | 负载均衡与存活探测 | 无 | `{ "status": "ok" }` |

---

## 3. 会话

| 接口名 | 方法 | 路径 | 描述 | 请求参数 | 返回格式 |
|--------|------|------|------|----------|----------|
| 创建会话 | `POST` | `/api/v1/sessions` | 新建会话线程，用于挂载消息与任务 | **Body**：`{ "title"?: string }` | `{ "session_id": string }` |
| 会话消息列表 | `GET` | `/api/v1/sessions/{session_id}/messages` | 会话级记忆（与 `messages` 表一致） | **Path**：`session_id`；**Query（可选）**：`limit`、`offset` 或 `before_id`（实现二选一约定即可） | `{ "messages": [ { "id", "role", "content", "created_at" } ] }` |

---

## 4. 任务

| 接口名 | 方法 | 路径 | 描述 | 请求参数 | 返回格式 |
|--------|------|------|------|----------|----------|
| 创建并启动任务 | `POST` | `/api/v1/tasks` | 创建任务并异步执行 Plan-and-Execute；写入用户消息并启动 Agent | **Body**：`{ "session_id": string, "user_message": string }` | `{ "task_id": string, "events_stream_path": string }`（`events_stream_path` 如 `/api/v1/tasks/{task_id}/events/stream`，便于前端拼 `VITE_API_BASE_URL`） |
| 任务列表 | `GET` | `/api/v1/tasks` | 仪表盘与列表页 | **Query**：`limit`、`offset`；`status?`（`pending`/`running`/`success`/`failed`/`cancelled`） | `{ "items": [ { "id", "session_id", "status", "summary", "plan_version", "created_at", "updated_at" } ], "total": number }` |
| 任务详情 | `GET` | `/api/v1/tasks/{task_id}` | 含当前计划结构，供详情页展示 | **Path**：`task_id` | `{ "id", "session_id", "status", "summary", "plan_version", "plan"?: { "steps": unknown[] }, "created_at", "updated_at", "error_message"?: string }`（`plan` 形状实现可细化，须可序列化展示） |
| 任务事件历史 | `GET` | `/api/v1/tasks/{task_id}/events` | 可观测事件分页/增量；与 `task_events` 一致 | **Path**：`task_id`；**Query**：`after_seq?`（仅返回 `seq > after_seq`）；可选 `limit` | `{ "events": [ { "seq", "ts", "module", "kind", "payload" } ] }` |

---

## 5. 实时事件流（SSE）

| 接口名 | 方法 | 路径 | 描述 | 请求参数 | 返回格式 |
|--------|------|------|------|----------|----------|
| 订阅任务事件 | `GET` | `/api/v1/tasks/{task_id}/events/stream` | 执行过程中推送事件；结构与 `task_events` 对齐 | **Path**：`task_id`；**Header**：`Accept: text/event-stream`；可选 **Query**：`after_seq` 或 `last_event_id`（均为「仅 `seq` 更大」）；可选 **Header**：`Last-Event-ID`（与 query 二选一，优先级：`after_seq` > `last_event_id` > 头） | **SSE**：`id` 为 `seq`；`event` 与 `kind` 对齐；`data` 为 JSON（与 GET `/events` 单条一致）。任务终态后短时无新事件则关闭流。 |

说明：客户端在断线后可调用 `GET /events?after_seq=<最后收到的 seq>` 补拉缺口，再重新订阅 SSE。

---

## 6. 设置（非密钥）

| 接口名 | 方法 | 路径 | 描述 | 请求参数 | 返回格式 |
|--------|------|------|------|----------|----------|
| 获取设置 | `GET` | `/api/v1/settings` | MCP/Skills 等**脱敏**配置（无 API Key 明文） | 无 | `{ "mcp": array, "skills_paths": string[], ... }`（与 `settings_kv` 允许暴露的键一致） |
| 更新设置 | `PUT` | `/api/v1/settings` | 更新非敏感配置 | **Body**：同 GET 可写字段（**禁止** body 含 LLM/MCP 密钥） | `{ "ok": true }` |

---

## 7. 工具注册表（只读）

| 接口名 | 方法 | 路径 | 描述 | 请求参数 | 返回格式 |
|--------|------|------|------|----------|----------|
| 列出工具 | `GET` | `/api/v1/tools` | 统一工具注册表展示：内置 / MCP / Skill 映射 | 无 | `{ "tools": [ { "name": string, "description": string, "source": "builtin" \| "mcp" \| "skill", "read_only"?: boolean } ] }`（`read_only` 等为 MVP 最小权限分级，可选） |

---

## 8. 附录：与数据模型对齐的枚举

与 [`TECH_DESIGN.md`](TECH_DESIGN.md) §3 一致，便于前后端与 OpenAPI 对齐：

| 字段/类型 | 取值说明 |
|-----------|----------|
| `tasks.status` | `pending` / `running` / `success` / `failed` / `cancelled` |
| `task_events.module` | `planning` / `memory` / `tool` / `execution` |
| `task_events.kind` | 如 `plan_created`、`step_start`、`tool_call`、`tool_result`、`error`、`replan` 等（实现可扩展，前端宜按 kind 做展示分支） |
| `messages.role` | `user` / `assistant` / `system` |
| 工具 `source` | `builtin` / `mcp` / `skill` |

---

*文档版本：MVP；多 Agent、完整租户与 OAuth 不在本文档默认路径内。*
