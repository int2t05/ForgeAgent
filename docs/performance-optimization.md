# ForgeAgent 性能优化方案

## 一、概述

本文档针对 ForgeAgent 项目中与 Agent 对话反馈速度相关的性能瓶颈进行诊断和优化。

### 性能瓶颈优先级

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | 数据库查询风暴 | SSE 期间每秒多次 DB 查询 |
| P0 | 频繁创建 DB 连接 | 每个任务 13+ 次连接创建 |
| P0 | SSE 轮询每次新建连接 | 30 秒任务产生 200+ 连接 |
| P0 | 每次 SSE 事件触发全组件重渲染 | UI 卡顿 |
| P1 | framework_router 阻塞启动 | 200-500ms 不必要延迟 |
| P1 | 重复查询相同数据 | 网络请求浪费 |
| P2 | useQueries 瀑布流 | N 个任务 = N 次并行查询 |
| P2 | 每次 SSE 事件扫描全量事件 | O(n) 复杂度 |

---

## 二、后端优化

### 2.1 P0: append_event 的 SELECT MAX(seq) 查询风暴

**问题**：`event_repository.py` 每次追加事件都要先执行 `SELECT MAX(seq)` 查询。在 LLM 流式输出时（~50 chars/sec），每秒产生多次 DB 查询。

```python
# 当前实现 (event_repository.py:18-22)
stmt = select(func.coalesce(func.max(TaskEvent.seq), 0)).where(TaskEvent.task_id == task_id)
result = await session.execute(stmt)
max_seq: int = result.scalar_one()
```

**优化方案**：使用 PostgreSQL 序列或应用层自增

```python
# 方案 A: PostgreSQL DEFAULT 序列自动递增
# migrations/xxx_add_task_event_seq.sql
ALTER TABLE task_events ALTER COLUMN seq SET DEFAULT nextval('task_event_seq'::regclass);

# 方案 B: 应用层原子计数器（推荐，跨数据库兼容）
class TaskEventRepository:
    async def append_event(self, db: AsyncSession, task_id: int, event: TaskEventCreate) -> TaskEvent:
        # 使用单条 INSERT + RETURNING，不分离查询
        stmt = (
            insert(TaskEvent)
            .values(task_id=task_id, event_type=event.event_type, data=event.data)
            .returning(TaskEvent.seq)  # 原子获取分配的 seq
        )
        result = await db.execute(stmt)
        allocated_seq = result.scalar_one()
        # 不需要额外 SELECT MAX
```

**预期效果**：消除 50% 的 DB 查询次数

---

### 2.2 P0: react_agent.py 每个任务创建 13+ 次 DB 连接

**问题**：`react_agent.py` 在多个位置（171, 200, 234, 246, 273, 320, 364, 382, 436, 463, 491 行）各自创建新的 `AsyncSessionLocal()` 连接。

```python
# 当前实现 - 每处都创建新连接
async def run_agent(...):
    async with AsyncSessionLocal() as db:  # 连接 1
        ...
        async with db.begin():
            await task_repository.update_status(...)  # 提交

    async with AsyncSessionLocal() as db:  # 连接 2
        ...

    # ... 更多独立连接
```

**优化方案**：传入共享连接，统一事务管理

```python
async def run_agent(task_id: int, user_message_id: int):
    # 整个任务使用单一连接
    async with AsyncSessionLocal() as db:
        async with db.begin():
            # 初始化
            task = await task_repository.get_task_by_id(db, task_id)

            # 主循环 - 使用同一个 db 连接
            while step < max_steps:
                reply = await chat.ainvoke(messages)  # LLM 调用

                # 所有事件写入使用同一事务
                await event_repository.append_event(db, task_id, ...)

                if is_final:
                    await task_repository.update_status(db, task_id, "success")
                    await message_repository.add_message(db, ...)
                    break

            # 事务自动提交
```

**预期效果**：
- 连接数从 13+ 降至 1
- 事务一致性更好
- 延迟降低 50-100ms

---

### 2.3 P0: SSE 轮询每次新建 DB 连接

**问题**：`event_stream_service.py` 每 150ms 轮询时都创建新连接。

```python
# 当前实现 (event_stream_service.py:67)
while True:
    async with AsyncSessionLocal() as db:  # 每轮新建连接！
        task = await task_repository.get_task_id(db, task_id)
        rows = await event_repository.list_events(db, task_id, after_seq=last_seq)
    await asyncio.sleep(_POLL_INTERVAL_SEC)
```

**优化方案**：使用单长连接 + 游标预读取

```python
# 优化后实现
async def iter_task_event_sse(task_id: int, after_seq: int = 0):
    # 复用连接而非频繁创建销毁
    async with AsyncSessionLocal() as db:
        last_seq = after_seq
        idle_rounds = 0

        while True:
            # 使用 hint 提高查询效率
            stmt = (
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id)
                .where(TaskEvent.seq > last_seq)
                .order_by(TaskEvent.seq)
                .limit(100)  # 批量预读
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

            for row in rows:
                yield format_sse_frame(row)
                last_seq = row.seq

            # 任务结束且无新事件时退出
            if not rows:
                idle_rounds += 1
                task = await task_repository.get_task_by_id(db, task_id)
                if task.status in TERMINAL_STATUSES and idle_rounds >= 3:
                    return
            else:
                idle_rounds = 0

            await asyncio.sleep(_POLL_INTERVAL_SEC)
```

**额外优化**：将轮询间隔从 150ms 调整为 100ms，减少延迟。

**预期效果**：
- 30 秒任务连接数从 200+ 降至 1
- 减少 TCP 握手开销 ~20ms/次

---

### 2.4 P1: framework_router_node 阻塞启动

**问题**：`framework_router.py` 在每个任务开始时都调用 LLM 做路由判断。

```python
# framework_router.py:59-60
msg = await chat.ainvoke(
    [SystemMessage(content=_FRAMEWORK_ROUTER_SYSTEM), *chat_messages]
)
```

**优化方案**：根据输入特征快速路由

```python
# 方案 A: 基于规则的快速路径
def classify_intent(user_message: str) -> str:
    msg_lower = user_message.lower().strip()

    # 简单命令直接跳过路由
    if msg_lower.startswith('/'):
        return msg_lower[1:].split()[0]

    # 代码执行类关键词 → react
    code_kw = ['write code', 'run', 'execute', 'python', 'javascript', 'function']
    if any(kw in msg_lower for kw in code_kw):
        return "react"

    # 搜索类 → simple
    search_kw = ['search', 'find', 'look up', 'google']
    if any(kw in msg_lower for kw in search_kw):
        return "simple"

    # 默认走完整流程
    return None  # 触发 LLM 路由

# 方案 B: 缓存频繁查询的路由结果
@lru_cache(maxsize=1000)
def cached_route(user_message_hash: int, message: str) -> str:
    return slow_llm_route(message)
```

**预期效果**：
- 简单查询绕过 LLM 路由：节省 200-500ms
- 复杂查询仍保持原有流程

---

## 三、前端优化

### 3.1 P0: 每次 SSE 事件触发全组件重渲染

**问题**：`ChatPage.tsx:546` 中 `liveTaskEvents` 直接引用触发整个组件树重渲染。

```typescript
// 当前实现
const liveTaskEvents = useComposerTaskStore((s) => s.liveTaskEvents)

// 问题：即使只是追加一个 delta，所有子组件都会重新渲染
{messages.map((m) => (/* 重渲染 */))}
{streamedLlm.thinking && (<pre>...</pre>)}
```

**优化方案**：使用 Zustand 细粒度选择器 + React.memo

```typescript
// composerTaskStore.ts - 拆分状态
interface ComposerTaskStore {
  // 细粒度状态
  llmThinking: string
  llmAnswer: string
  latestSeq: number
  // ...
}

// ChatPage.tsx - 只订阅关心的部分
const llmThinking = useComposerTaskStore((s) => s.llmThinking)
const llmAnswer = useComposerTaskStore((s) => s.llmAnswer)

// 流式增量合并在 store 内部完成，不触发组件重渲染
setLiveEvents: (events) =>
  set((state) => {
    const { thinking, answer } = foldLlmStreamDeltas(events)
    return {
      llmThinking: thinking,
      llmAnswer: answer,
      latestSeq: events[events.length - 1]?.seq ?? state.latestSeq,
    }
  }),
```

**或使用 Reselect 模式**：

```typescript
// 消息列表单独 memo
const MessageList = React.memo(({ messages }) => (
  <>{messages.map((m) => <MessageBubble key={m.id} message={m} />)}</>
))

// 只在 thinking/answer 变化时更新
const StreamPreview = React.memo(({ thinking, answer }) => (
  <div>
    {thinking && <pre>{thinking}</pre>}
    {answer && <Markdown content={answer} />}
  </div>
))
```

**预期效果**：流式输出期间 CPU 占用降低 60-80%

---

### 3.2 P1: 重复 getTask 查询

**问题**：`ChatPage.tsx:375-402` 中 `taskPlanDetailQueries` 和 `latestSessionTaskDetailQuery` 查询同一个任务。

```typescript
// taskPlanDetailQueries 已包含 latest task
const taskPlanDetailQueries = useQueries({
  queries: tasksChrono.map((t) => ({
    queryKey: ['task', t.id],
    queryFn: () => getTask(t.id),
  })),
})

// 重复查询！
const latestSessionTaskDetailQuery = useQuery({
  queryKey: ['task', latestSessionTaskId],
  queryFn: () => getTask(latestSessionTaskId!),
})
```

**优化方案**：直接从 `taskPlanDetailQueries` 结果中提取

```typescript
const latestTaskQuery = useMemo(() => {
  if (!latestSessionTaskId) return null
  return taskPlanDetailQueries.find(
    (q) => q.queryKey[1] === latestSessionTaskId
  )
}, [taskPlanDetailQueries, latestSessionTaskId])
```

**预期效果**：减少 1 次不必要的网络请求

---

### 3.3 P1: Initial REST Fetch + SSE Gap Check 重复

**问题**：`usePendingComposerTaskSync.ts` 先 REST 获取全量事件，再 SSE 从断点继续，然后结束后再查一次 Gap。

```typescript
// 1. REST 获取全量（可能 200+ 条）
const initial = await getAllTaskEvents(taskId)  // 循环直到 <200

// 2. SSE 从断点继续
const startAfter = maxSeqInMap(bySeq)
await consumeTaskEventStream(streamUrl, startAfter, ...)

// 3. 结束后又查一次 Gap
const gap = await getAllTaskEvents(taskId, lastSeq)  // 又全量！
```

**优化方案**：SSE 结束后不需要 Gap 检查

```typescript
// SSE 连接是可靠的有序传输，不需要 gap 检查
await consumeTaskEventStream(streamUrl, startAfter, ...)

// SSE 正常结束意味着所有事件已接收
// 删除 gap 检查逻辑
```

**预期效果**：
- 减少 1 次全量 REST 请求（省 50-200ms）
- 简化代码逻辑

---

### 3.4 P2: useQueries 瀑布流

**问题**：`ChatPage.tsx:375` 对会话中的每个 Task 都发起并行查询。

```typescript
const taskPlanDetailQueries = useQueries({
  queries: tasksChrono.map((t) => ({
    queryKey: ['task', t.id],
    queryFn: () => getTask(t.id),
    staleTime: 5 * 60 * 1000,  // 5 分钟缓存
  })),
})
```

**优化方案**：仅在视口内查询可见任务

```typescript
// 使用 Intersection Observer 延迟加载
const visibleTaskIds = useRef(new Set<number>())

const taskPlanDetailQueries = useQueries({
  queries: [...visibleTaskIds.current].map((id) => ({
    queryKey: ['task', id],
    queryFn: () => getTask(id),
    staleTime: 5 * 60 * 1000,
  })),
})

// 或者批量查询
const allTaskDetails = useQuery({
  queryKey: ['tasks', sessionId, 'details'],
  queryFn: () => getTasksBySession(sessionId),  // 后端批量接口
})
```

---

## 四、网络传输优化

### 4.1 LLM 流式增量事件 Payload 太小

**问题**：`nodes.py` 每 480 字符或 120ms 刷新一次，产生大量小 Payload。

```python
# 当前
if self._buf_chars >= 480 or (now - self._last_flush) >= 0.12:
    await self.flush()
```

**优化方案**：

```python
# 增大阈值，减少事件数量
if self._buf_chars >= 1200 or (now - self._last_flush) >= 0.25:
    await self.flush()
```

**预期效果**：事件数量减少 50%，SSE 消息频率降低

---

### 4.2 JSON 解析重复

**问题**：后端序列化和前端反序列化不对称

```python
# 后端
"payload": payload_json_to_dict(row.payload_json)  # str → dict

# 前端
const parsed: unknown = JSON.parse(jsonStr)  # dict → string → dict
```

**优化方案**：统一格式，后端直接返回 JSON 字符串

```python
# 后端直接返回字符串，前端 parse 一次
"payload": row.payload_json  # 已经是字符串
```

---

## 五、综合优化路线图

### Phase 1: P0 关键修复（1-2 天）

| 优化项 | 预期效果 |
|--------|----------|
| append_event SELECT MAX 消除 | DB 查询减少 50% |
| SSE 连接复用 | 30s 任务连接从 200+ 降至 1 |
| 前端细粒度状态订阅 | 流式渲染 CPU 降 60% |

### Phase 2: P1 重要改进（2-3 天）

| 优化项 | 预期效果 |
|--------|----------|
| framework_router 快速路径 | 简单查询省 200-500ms |
| react_agent 连接复用 | 延迟降低 50-100ms |
| 消除重复查询 | 请求数减少 |

### Phase 3: P2 持续改进（1 周）

| 优化项 | 预期效果 |
|--------|----------|
| 批量查询 API | 减少 N+1 |
| SSE Payload 压缩 | 带宽降低 |
| Intersection Observer 懒加载 | 首屏更快 |

---

## 六、预期性能提升

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 首次响应延迟 | 800-1500ms | 300-600ms | 2-3x |
| 流式输出延迟 | 150-300ms | 50-100ms | 3x |
| 30s 任务 DB 连接数 | 200+ | 2-3 | 100x |
| 流式期间 CPU 占用 | 高 | 低 | 60% 降 |
| 并发会话支持数 | ~50 | ~200 | 4x |

---

## 七、数据库索引建议

```sql
-- 已有索引 (如不存在需添加)
CREATE INDEX IF NOT EXISTS idx_task_events_task_id_seq
ON task_events(task_id, seq);

CREATE INDEX IF NOT EXISTS idx_messages_session_id_id
ON messages(session_id, id);

CREATE INDEX IF NOT EXISTS idx_tasks_session_id
ON tasks(session_id);
```

---

## 八、监控指标建议

```python
# 添加关键性能指标埋点
metrics = {
    "task_created_to_first_event_ms": elapsed,
    "llm_first_token_ms": elapsed,
    "db_connections_per_task": count,
    "sse_events_per_second": rate,
    "events_per_task": total,
}
```
