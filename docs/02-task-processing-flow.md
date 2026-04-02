# ForgeAgent 任务处理流程

## 一、整体架构

```
API Layer (tasks.py)
    └── Service Layer (task_service.py)
            └── Agent Layer (LangGraph Workflow)
                    ├── Planner Node
                    ├── Actor Node
                    └── Learner Node
            └── Event Stream (SSE)
            └── Persistence (repositories)
```

---

## 二、任务创建

### 2.1 API 入口

**文件**: `backend/app/api/v1/tasks.py`

```python
@router.post("", response_model=TaskCreateResponse)
async def post_task(body: TaskCreate) -> TaskCreateResponse:
    return await task_service.create_task_start_mock(
        body.session_id,
        body.user_message,
        reuse_user_message_id=body.reuse_user_message_id,
    )
```

### 2.2 服务实现

**文件**: `backend/app/services/task_service.py`

```python
async def create_task_start_mock(session_id, user_message, *, reuse_user_message_id=None):
    # 1. 校验输入
    content = (user_message or "").strip()
    if not content:
        raise AppHTTPException(...)

    # 2. 生成任务 ID
    task_id = str(uuid4())
    stream_path = f"/api/v1/tasks/{task_id}/events/stream"

    async with AsyncSessionLocal() as db:
        async with db.begin():
            # 3. 校验会话存在
            chat = await session_repository.get_session_by_id(db, session_id)

            # 4. 创建用户消息
            user_msg = await message_repository.add_message(...)
            source_mid = user_msg.id

            # 5. 持久化任务（状态 running）
            task_row = Task(
                id=task_id,
                session_id=session_id,
                status="running",
                plan_version=1,
                source_user_message_id=source_mid,
                owns_source_user_message=True,
            )
            await task_repository.add_task(db, task_row)

    # 6. 调度后台 Agent 执行
    _schedule_run_agent_task(task_id, session_id, content)
    return TaskCreateResponse(task_id=task_id, events_stream_path=stream_path)
```

---

## 三、异步执行机制

### 3.1 后台任务调度

```python
def _schedule_run_agent_task(task_id, session_id, content):
    task = asyncio.create_task(run_agent_task(task_id, session_id, content))
    _AGENT_BACKGROUND_TASKS.add(task)
    task.add_done_callback(lambda t: _AGENT_BACKGROUND_TASKS.discard(t))
```

### 3.2 Agent 执行函数

```python
async def run_agent_task(task_id, session_id, user_message):
    settings = get_settings()
    graph = get_compiled_agent_graph()  # LangGraph
    config = {"configurable": {"thread_id": task_id}}

    # 1. 构造初始状态
    initial = {
        "task_id": task_id,
        "session_id": session_id,
        "user_message": user_message,
        "replan_count": 0,
        "max_replan_attempts": settings.max_replan_attempts,
        "blackboard_notes": list(seed_notes),  # 从会话加载
        "actor_tool_trace": [],
    }

    # 2. 检查是否已完成（checkpoint 恢复）
    snap = await graph.aget_state(config)
    if snap.values and not snap.next:
        result = dict(snap.values)
    else:
        result = await _run_agent_graph_to_completion(graph, config, task_id, initial)

    # 3. 更新任务状态
    async with AsyncSessionLocal() as db:
        task = await task_repository.get_task_by_id(db, task_id)
        if outcome == "success":
            task.status = "success"
            task.summary = result.get("summary")
        elif outcome == "failed":
            task.status = "failed"
            task.error_message = result.get("error_message")
```

### 3.3 LangGraph Stream 执行

```python
async def _run_agent_graph_to_completion(graph, config, *, task_id, stream_input):
    async with AsyncSessionLocal() as db:
        async for update in graph.astream(stream_input, config, stream_mode="updates"):
            if isinstance(update, dict):
                await _persist_langgraph_stream_updates(db, task_id, update)
```

---

## 四、工作流定义

**文件**: `backend/app/modules/workflow/graph.py`

```
START → planner → actor → learner
                        ↓
              条件边 route_after_learner
                   ↙          ↘
               planner        END
```

```python
def build_agent_graph(...):
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("actor", actor)
    builder.add_node("learner", learner)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "actor")
    builder.add_edge("actor", "learner")
    builder.add_conditional_edges(
        "learner",
        route_after_learner,
        {"planner": "planner", "done": END},
    )
    return builder
```

---

## 五、AgentState 定义

**文件**: `backend/app/modules/workflow/state.py`

```python
class AgentState(TypedDict, total=False):
    task_id: str
    session_id: str
    user_message: str
    replan_count: int              # 已重规划次数
    max_replan_attempts: int      # 最大重规划上限
    plan_steps: list[dict]        # 计划步骤
    current_step_index: int
    blackboard_notes: list[str]    # 共享黑板（跨任务）
    actor_tool_trace: list[dict]   # 工具执行轨迹
    replan_requested: bool         # 是否请求重规划
    outcome: Literal["success", "failed"]
    summary: str | None
    error_message: str | None
```

---

## 六、任务状态流转

```
创建任务 → running
    ↓
┌────────────────────────────────────────┐
│         LangGraph Workflow              │
│                                        │
│  planner → actor → learner            │
│       ↑         │    │                │
│       └─────────┘    ↓                │
│              (replan_requested?)       │
│                    │                   │
│                    ↓                   │
│                 END                    │
└────────────────────────────────────────┘
    ↓                    ↓
success              failed
```

**状态枚举**: `pending`, `running`, `success`, `failed`, `cancelled`

---

## 七、SSE 事件推送

### 7.1 API 入口

**文件**: `backend/app/api/v1/tasks.py`

```python
@router.get("/{task_id}/events/stream")
async def get_task_events_stream(task_id, request: Request, ...):
    start_after = after_seq or parse_last_event_id(request)
    generator = event_stream_service.iter_task_event_sse(task_id, after_seq=start_after)
    return StreamingResponse(generator, media_type="text/event-stream", ...)
```

### 7.2 SSE 生成器

**文件**: `backend/app/services/event_stream_service.py`

```python
async def iter_task_event_sse(task_id, *, after_seq):
    last_seq = after_seq
    stable_empty_rounds = 0

    async with AsyncSessionLocal() as db:
        while True:
            task = await task_repository.get_task_by_id(db, task_id)
            if task is None:
                return

            # 拉取新事件
            rows = await event_repository.list_events(db, task_id, after_seq=last_seq, limit=200)

            if rows:
                stable_empty_rounds = 0
                for row in rows:
                    yield _format_sse_message(event=row.kind, event_id=row.seq, data=data)
                    last_seq = row.seq
                await asyncio.sleep(_POLL_INTERVAL_SEC)
                continue

            # 无新事件：终态任务空转 4 轮后关闭
            if task.status in TERMINAL_STATUSES:
                stable_empty_rounds += 1
                if stable_empty_rounds >= 4:
                    return
            await asyncio.sleep(_POLL_INTERVAL_SEC)
```

### 7.3 常见事件类型

| Module | Kind | 说明 |
|--------|------|------|
| planning | plan_created | 计划已生成 |
| planning | replan | 触发重规划 |
| execution | step_start | 步骤开始 |
| execution | step_end | 步骤结束 |
| execution | llm_stream_delta | LLM 流式输出 |
| execution | react_turn | ReAct 循环轮次 |
| memory | reflection | Learner 反思 |
| workflow | node_update | 节点状态更新 |

---

## 八、完整时序图

```
Client              API              TaskService         LangGraph          Repository         SSE
  │                  │                   │                  │                  │               │
  │──POST /tasks───▶│                   │                  │                  │               │
  │                  │──create_task──────▶│                  │                  │               │
  │                  │                   │──add_task────────▶│                  │               │
  │                  │◀──task_id────────│                  │                  │               │
  │◀────────────────│                   │                  │                  │               │
  │                  │                   │──asyncio.create_task()              │               │
  │                  │                   │       │          │                  │               │
  │                  │                   │       └──run_agent_task()          │               │
  │                  │                   │              │          │               │               │
  │                  │                   │              │  graph.astream(stream_mode='updates')
  │                  │                   │              │          │               │               │
  │                  │                   │              │──append_event()───────▶│               │
  │                  │                   │              │          │               │               │
  │──GET /events/stream────────────────▶│              │          │               │               │
  │                  │                   │              │◀──list_events(after_seq)──┐               │
  │◀──SSE stream────│                   │              │──events──────────────────▶│               │
```
