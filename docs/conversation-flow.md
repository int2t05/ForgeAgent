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

### TaskEvent 类型

| 事件类型 | 说明 |
|----------|------|
| `thinking` | Agent 思考过程 |
| `plan` | 执行计划 |
| `replan` | 重规划原因和结果 |
| `llm_stream_delta` | LLM 流式输出增量 |
| `tool_call` | 工具调用 |
| `tool_result` | 工具执行结果 |
| `status_change` | 任务状态变更 |

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
 │                      │  {session_id, msg_id} │                       │
 │                      │─────────────────────>│                       │
 │                      │                       │                       │
 │                      │                       │  创建 Task            │
 │                      │                       │  写入 task_events     │
 │                      │                       │──────────────────────>│
 │                      │                       │                       │
 │                      │                       │                       │  LangGraph 执行
 │                      │                       │                       │  ├─ thinking
 │                      │                       │                       │  ├─ plan
 │                      │                       │                       │  ├─ replan（如需）
 │                      │                       │                       │  ├─ tool_call
 │                      │                       │                       │  └─ llm_stream_delta
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

### 阶段一：用户发送消息

**前端 (ChatPage.tsx):**

```typescript
const handleSend = async (content: string) => {
  // 1. 保存用户消息到服务器
  await createMessage(sessionId, { role: 'user', content })

  // 2. 创建任务并触发 Agent 执行
  const task = await createTask(sessionId, {
    message_id: userMessageId,
    top_k: 5,
  })

  // 3. 开始消费 SSE 实时事件
  await consumeTaskEvents(task.id)
}
```

**后端 (sessions.py POST):**

```python
@router.post("/{session_id}/messages")
async def add_message(session_id: int, data: MessageCreate, db: AsyncSession):
    # 保存用户消息，返回消息 ID
    message = await message_repository.add_message(db, session_id, **data)
    return message
```

---

### 阶段二：创建任务并触发执行

**前端 (tasks.ts):**

```typescript
export const createTask = async (sessionId: number, data: TaskCreate) => {
  const res = await api.post(`/tasks`, { session_id: sessionId, ...data })
  return res.data
}
```

**后端 (tasks.py POST):**

```python
@router.post("")
async def create_task(data: TaskCreate, db: AsyncSession):
    task = await task_service.create_and_start(db, data)
    return task
```

**后端 (task_service.py):**

```python
async def create_and_start(db, data: TaskCreate):
    # 1. 查找关联的用户消息
    user_message = await message_repository.get(db, data.message_id)

    # 2. 收集对话历史（最近 N 条）
    history = await message_repository.list_messages(db, session_id, limit=10)

    # 3. 创建 Task 记录
    task = await task_repository.create(db, session_id, user_message.content)

    # 4. 异步启动 LangGraph 执行
    asyncio.create_task(run_agent(db, task.id, user_message, history))

    return task
```

---

### 阶段三：Agent 执行（LangGraph）

**执行流程 (task_service.py):**

```python
async def run_agent(db, task_id, user_message, history):
    # 1. 初始化 LangGraph
    graph = build_agent_graph()

    # 2. 构造初始状态
    initial = {
        "task_id": task_id,
        "user_message": user_message.content,
        "history": format_history(history),  # 格式化为 [user, assistant, user, ...]
        "events": [],                         # 收集所有事件
        "plan": None,
    }

    # 3. 执行图
    result = await graph.ainvoke(initial)

    # 4. 更新 Task 状态
    task.status = "success" if result.get("outcome") == "success" else "failed"
    task.summary = result.get("summary")
```

**Agent 节点 (nodes.py):**

| 节点 | 说明 |
|------|------|
| `thinking_node` | 分析用户请求，提取关键信息 |
| `plan_node` | 生成执行计划 |
| `replan_node` | 评估计划，如需调整则重新规划 |
| `execute_node` | 执行计划中的步骤 |
| `final_node` | 生成最终回复 |

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

**前端消费 (usePendingComposerTask.ts):**

```typescript
// 1. 初始批量拉取历史事件
const historical = await getTaskEvents(taskId, 0, 200)

// 2. 建立 SSE 连接
const stream = new EventSource(buildStreamUrl(taskId, lastSeq))
stream.onmessage = (e) => {
  const event = JSON.parse(e.data)
  eventStore.apply(event)  // 合并到本地状态
}
```

---

### 阶段五：对话记忆持久化

**任务完成后写入会话消息 (task_service.py):**

```python
async def create_and_start(db, task_id, user_message, history):
    # ... Agent 执行 ...
    result = await graph.ainvoke(initial)

    # 将助手回复写入消息表（对话记忆）
    if result.get("outcome") == "success":
        await message_repository.add_message(
            db,
            session_id=session_id,
            role="assistant",
            content=result.get("summary"),
        )
```

---

## 四、前端状态管理

### 三层状态架构

```
┌─────────────────────────────────────────────┐
│         TanStack Query (服务端状态)          │
│   - useSession()      会话列表/详情          │
│   - useMessages()    消息列表（持久化）      │
│   - useTask()        任务详情               │
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
├── id           主键
├── title        会话标题
├── created_at   创建时间
└── updated_at   更新时间
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
├── id           主键
├── task_id      外键 → tasks.id
├── seq          序号（保证顺序）
├── event_type   事件类型
├── data         事件数据 (JSON)
└── created_at   创建时间
```

---

## 七、架构特点总结

1. **前后端分离 + 双通道通信**
   - REST API：用于 CRUD 操作（消息管理、会话管理）
   - SSE：用于实时推送任务执行过程

2. **LangGraph Plan-and-Execute 模式**
   - 先规划再执行，支持条件重规划
   - 状态机驱动，事件化记录执行过程

3. **对话记忆与任务追踪分离**
   - `messages` 表：持久化对话历史（用于上下文）
   - `task_events` 表：记录执行细节（用于调试/展示）

4. **流式输出分阶段展示**
   - `thinking` 事件 → 展示 AI 思考过程
   - `llm_stream_delta` 事件 → 实时渲染回复内容

5. **前端状态分层管理**
   - TanStack Query：服务端状态同步
   - Zustand：实时状态（当前任务事件）
   - React State：UI 本地状态
