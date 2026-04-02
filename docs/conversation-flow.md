# ForgeAgent 对话业务流程文档

## 一、项目概述

ForgeAgent 是一个基于 LangGraph 的 AI Agent 对话系统，支持流式输出、实时事件推送和对话记忆持久化。

### 核心特性
- **Plan-and-Execute 模式**：Agent 先规划后执行，支持条件重规划
- **SSE 实时推送**：前端通过 Server-Sent Events 实时接收任务执行事件
- **对话记忆**：用户消息和 Agent 回复持久化到数据库，支持上下文关联
- **流式输出**：LLM 响应支持 thinking 和 answer 分阶段展示

---

## 二、核心概念

| 概念 | 说明 |
|------|------|
| **Session** | 对话会话，包含会话元信息（标题、创建时间等） |
| **Message** | 对话消息，归属到特定 Session，支持 role（user/assistant/system）|
| **Task** | 任务实例，关联 Session，是 Agent 执行的基本单位 |
| **TaskEvent** | 任务事件，记录 Agent 执行过程中的每个步骤 |

### TaskEvent（`task_events` 行）

每条事件含 **`module`**（`planning` / `memory` / `tool` / `execution` / `workflow`）与 **`kind`**（字符串），payload 为 JSON。常见 **kind** 包括：

| kind | 说明 |
|------|------|
| `plan_created` | 规划产出步骤列表 |
| `replan` | 重规划记账（含 `plan_version` 等） |
| `step_start` / `step_end` | 执行步骤起止 |
| `tool_call` / `tool_result` | 工具调用与结果（多轮重试可多条 `tool_result`） |
| `llm_stream_delta` | 流式片段（payload 含 `phase`：`thinking` / `action` / `answer` 等） |
| `error` | 错误简述 |
| `node_update` | LangGraph 节点完成后的状态增量摘要（`module=workflow`） |

---

## 三、对话业务流程

### 完整链路时序图

```
用户                    前端                   后端 API                Agent/LLM
 │                      │                       │                       │
 │  输入消息            │                       │                       │
 │─────────────────────>│                       │                       │
 │                      │                       │                       │
 │                      │  POST /sessions/{id}/messages                │
 │                      │  (role=user)          │                       │
 │                      │─────────────────────>│                       │
 │                      │                       │                       │
 │                      │                       │  保存用户消息          │
 │                      │                       │───────────────────────>│
 │                      │                       │                       │
 │                      │  POST /tasks          │
 │                      │  {session_id, user_message, reuse_user_message_id?} │
 │                      │─────────────────────>│                       │
 │                      │                       │                       │
 │                      │                       │  创建 Task            │
 │                      │                       │  写入 task_events     │
 │                      │                       │──────────────────────>│
 │                      │                       │                       │
 │                      │                       │                       │  LangGraph：planner → actor → learner
 │                      │                       │                       │  ├─ plan_created / replan
 │                      │                       │                       │  ├─ step_* / tool_call / tool_result
 │                      │                       │                       │  ├─ llm_stream_delta
 │                      │                       │                       │  ├─ node_update（workflow）
 │                      │                       │                       │  └─ 条件回 planner 或结束
 │                      │                       │                       │
 │                      │                       │  TaskEvent 持久化      │
 │                      │                       │<───────────────────────│
 │                      │                       │                       │
 │  GET /tasks/{id}/events/stream (SSE)         │                       │
 │<─────────────────────────────────────────────│                       │
 │                      │                       │                       │
 │                      │  SSE 实时推送事件      │                       │
 │                      │<───────────────────────────────────────────────│
 │                      │                       │                       │
 │                      │                       │                       │
 │                      │                       │  Task 完成            │
 │                      │                       │  写入 summary          │
 │                      │                       │                       │
 │                      │                       │  写入 assistant 消息  │
 │                      │                       │  (对话记忆)            │
 │                      │                       │                       │
 │  GET /sessions/{id}/messages                 │                       │
 │<─────────────────────────────────────────────│                       │
 │                      │                       │                       │
```

---

### 阶段一：用户发送消息（可选：先落库再起任务）

常见路径：先 `POST /api/v1/sessions/{id}/messages` 写入用户消息，再 **`POST /api/v1/tasks`** 携带同一段 `user_message`（或由服务在单事务内写入消息，见 OpenAPI）。也支持 **`reuse_user_message_id`**：复用已有用户消息、截断后续对话并重跑 Agent。

**前端**：`TaskCreateBody` 为 `{ session_id, user_message, reuse_user_message_id? }`（见 `frontend/src/types/task.ts`）。

---

### 阶段二：创建任务并触发执行

**API**：`POST /api/v1/tasks` → `task_service.create_and_start`：创建 `tasks` 行、写用户消息（若适用）、`asyncio.create_task` 后台执行编译图；响应 **`task_id`** 与 **`events_stream_path`**（相对路径）。

---

### 阶段三：Agent 执行（LangGraph Plan-Act-Learn）

**图结构**：`planner` → `actor` → `learner`；`learner` 后若 `replan_requested` 且未失败则回到 `planner`（受 `max_replan_attempts` 约束）。

**运行时**：`get_compiled_agent_graph().astream(..., stream_mode="updates")`；每次节点完成由服务层写入 **`node_update`**；Planner 侧在需要时写入 **`replan`** 并递增 `plan_version`。

| 节点 | 说明 |
|------|------|
| `planner` | 会话历史 + 黑板要点 → 计划步骤；重规划时先 bump 版本 |
| `actor` | 逐步工具调用与流式总结（`llm_stream_delta`） |
| `learner` | 反思、更新黑板（会话持久化）、设置是否再规划 |

---

### 阶段四：SSE 实时推送

**后端 SSE 生成器 (event_stream_service.py):**

```python
async def iter_task_event_sse(task_id, after_seq=0):
    last_seq = after_seq
    stable_rounds = 0

    while True:
        rows = await event_repository.list_events(db, task_id, after_seq=last_seq)

        for row in rows:
            yield format_sse_frame(row)  # event: task_event, data: JSON

        # 任务结束且稳定时退出
        if task.status in TERMINAL_STATUSES:
            stable_rounds += 1
            if stable_rounds > 4:
                return

        await asyncio.sleep(0.15)  # 轮询间隔
```

**前端**：任务详情页等通过 **`useTaskTimeline`**（或等价 Hook）先 `GET …/events`，再 `GET …/events/stream`（SSE），按 **`seq`** 去重合并；_chat 首屏流式展示依赖折叠 `llm_stream_delta` 等工具函数。

---

### 阶段五：对话记忆与黑板

- **`messages` 表**：用户与助手轮次持久化；Planner 通过 `SessionLLMContextManager` 读取最近消息。
- **`sessions.blackboard_notes_json`**：Learner 跨任务写入的要点；任务过程中从 checkpoint / 状态合并，结束后可 flush 回会话行。

---

## 四、前端状态管理

### 三层状态架构

```
┌─────────────────────────────────────────────┐
│         TanStack Query (服务端状态)          │
│   - useSession()       当前会话             │
│   - 会话消息 / 任务相关 Query               │
│   - useTaskDetail()    任务详情             │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│         Zustand Stores (前端运行时状态)       │
│   - sessionStore     当前选中会话            │
│   - composerTaskStore  任务+SSE事件实时状态  │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│              React Components               │
│   - ChatPage          聊天主界面             │
│   - MessageBubble     消息气泡               │
│   - TaskEventRow      任务事件行             │
└─────────────────────────────────────────────┘
```

### 流式消息渲染

```typescript
// ChatPage.tsx
const { liveTaskEvents } = useComposerTaskStore()

// 将 SSE 事件合并为 thinking 和 answer
const streamed = useMemo(
  () => foldLlmStreamDeltas(liveTaskEvents),
  [liveTaskEvents]
)

// 渲染中
{busy && (
  <div>
    {streamed.thinking && <pre>{streamed.thinking}</pre>}
    {streamed.answer && <Markdown>{streamed.answer}</Markdown>}
  </div>
)}
```

---

## 五、API 端点汇总

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sessions` | 分页列出会话 |
| POST | `/api/v1/sessions` | 创建新会话 |
| GET | `/api/v1/sessions/{id}` | 获取会话详情 |
| PATCH | `/api/v1/sessions/{id}` | 更新会话标题 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |

### 消息管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sessions/{id}/messages` | 获取消息列表 |
| POST | `/api/v1/sessions/{id}/messages` | 追加消息（不触发 Agent）|
| PATCH | `/api/v1/sessions/{id}/messages/{mid}` | 更新消息 |
| DELETE | `/api/v1/sessions/{id}/messages/{mid}` | 删除消息 |

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/tasks` | 分页列出任务 |
| POST | `/api/v1/tasks` | **创建任务并异步执行 Agent** |
| GET | `/api/v1/tasks/{id}` | 获取任务详情（含 plan）|
| PATCH | `/api/v1/tasks/{id}` | 取消任务；若该任务对应「本轮新建」用户消息，删除该条及之后消息并在响应体 `restored_user_message` 中带回正文供前端恢复输入框 |
| DELETE | `/api/v1/tasks/{id}` | 删除已结束任务 |

### 任务事件（SSE）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/tasks/{id}/events` | 获取任务事件历史 |
| GET | `/api/v1/tasks/{id}/events/stream` | **SSE 实时事件流** |

---

## 六、数据库模型

### Session（会话）

```sql
sessions
├── id                         TEXT PK
├── title                      TEXT NULL
├── blackboard_notes_json      TEXT NULL  -- Learner 会话级黑板
├── created_at                  DATETIME
└── （无 ORM 级 updated_at 时以实际迁移为准）
```

### Message（消息）

```sql
messages
├── id           主键
├── session_id   外键 → sessions.id
├── role         角色 (user/assistant/system)
├── content      内容
└── created_at   创建时间
```

### Task（任务）

```sql
tasks
├── id           主键
├── session_id   外键 → sessions.id
├── status       状态 (pending/running/success/failed/cancelled)
├── source_user_message_id  触发任务的用户消息（可空）
├── owns_source_user_message  是否为本轮新建用户消息（取消时可回滚删除）
├── plan         执行计划 (JSON)
├── summary      最终摘要
└── created_at   创建时间
```

### TaskEvent（任务事件）

```sql
task_events
├── id             INTEGER PK
├── task_id        FK → tasks.id
├── seq            INTEGER  -- 任务内单调
├── ts             DATETIME
├── module         TEXT     -- planning | memory | tool | execution | workflow
├── kind           TEXT     -- plan_created, replan, step_*, tool_*, llm_stream_delta, node_update, error, ...
└── payload_json   TEXT NULL
```

---

## 七、架构特点总结

1. **前后端分离 + 双通道通信**
   - REST API：用于 CRUD 操作（消息管理、会话管理）
   - SSE：用于实时推送任务执行过程

2. **LangGraph Plan-and-Execute 模式**
   - 先规划再执行，支持条件重规划
   - 状态机驱动，事件化记录执行过程

3. **对话记忆、黑板与任务追踪分离**
   - `messages`：轮次对话；`sessions.blackboard_notes_json`：Learner 结构化要点
   - `task_events`：可观测时间线（含 `node_update` 图级增量）

4. **流式输出分阶段展示**
   - `llm_stream_delta` 的 `phase` 字段区分 thinking / answer 等，由前端折叠渲染

5. **前端状态分层管理**
   - TanStack Query：服务端状态同步
   - Zustand：实时状态（当前任务事件）
   - React State：UI 本地状态
