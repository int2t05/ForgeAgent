# ForgeAgent Agent 响应速度优化方案

## 一、当前瓶颈分析

### 1.1 典型响应时间分解

假设：2 步计划，每步 2 个工具调用，无重试

| 阶段 | 延迟 |
|------|------|
| POST /tasks (API) | ~50ms |
| Planner LLM | ~2s |
| Actor 第 1 步 (2 工具) | ~3.3s |
| Actor 第 2 步 (2 工具) | ~3.3s |
| 总结 LLM | ~2s |
| Learner LLM | ~2s |
| 终态 SSE 关闭延迟 | +400ms |
| **总计** | **~13-16s** |

### 1.2 关键瓶颈

| 优先级 | 瓶颈 | 影响 |
|--------|------|------|
| P0 | SSE 轮询间隔 100ms | 事件推送最大延迟 100ms |
| P0 | 每工具调用独立 DB 事务 | 11 条事件/步 × ~15ms = ~165ms |
| P1 | ReAct 串行执行 | 工具间无并行 |
| P1 | LLM 重试退避过长 | 429/5xx 时最长 60s |
| P2 | Planner JSON 重试 | 最多 3 次 LLM 调用 |
| P2 | Learner 反思 LLM | 额外 1-3 次调用 |

---

## 二、LangGraph 并行执行优化

### 2.1 工具并行执行

**当前问题**：ReAct 循环中工具串行执行

```python
# 当前实现 - 串行
if invocations:
    for tn, args in invocations:  # ← 串行
        final_ok, last_exec = await run_single_tool_with_retry(...)
```

**优化方案**：使用 `asyncio.gather` 并行执行独立工具

```python
# modules/execution/step_react_loop.py

if invocations:
    # 并行执行所有工具调用
    tasks = [
        run_single_tool_with_retry(
            task_id, step_id, tn, args, max_tool_tries,
            react_thought=thought_round,
        )
        for tn, args in invocations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for (tn, args), result in zip(invocations, results):
        if isinstance(result, Exception):
            call_results.append({"tool": tn, "error": str(result), "ok": False})
        else:
            ok, exec_out, attempt_rows = result
            call_results.append({...})
```

**预期效果**：2 个独立工具从 ~600ms 降至 ~300ms（取最大值而非累加）

---

### 2.2 计划步骤并行执行（条件允许时）

**当前问题**：步骤按顺序串行执行

```python
# 当前实现 - 串行
for step in plan_steps:  # ← 串行
    result = await execute_plan_step_react(...)
```

**优化方案**：独立步骤并行执行

```python
# modules/execution/nodes.py

# 识别独立步骤（无依赖关系的步骤可并行）
independent_steps = []
dependent_steps = []

for i, step in enumerate(plan_steps):
    if _has_no_dependencies(step, plan_steps[:i]):
        independent_steps.append(step)
    else:
        dependent_steps.append((i, step))

# 并行执行独立步骤
if independent_steps:
    tasks = [
        execute_plan_step_react(task_id, step, ...)
        for step in independent_steps
    ]
    results = await asyncio.gather(*tasks)

# 串行执行依赖步骤
for step in dependent_steps:
    result = await execute_plan_step_react(...)
```

**注意**：需确保步骤之间无数据依赖，且理解用户期望逐步执行

---

### 2.3 并行 LLM 调用

当需要多个独立 LLM 判断时：

```python
# 示例：同时查询多个工具的描述
async def gather_tool_descriptions(tools: list[str]) -> dict[str, str]:
    tasks = {name: describe_tool(name) for name in tools}
    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))
```

---

## 三、数据库写入优化

### 3.1 批量事件写入

**当前问题**：每条事件独立事务

```python
# 当前 - 每条事件独立事务
await event_repository.append_event(db, task_id, "tool", "tool_call", ...)
await event_repository.append_event(db, task_id, "tool", "tool_result", ...)
```

**优化方案**：批量写入

```python
# repositories/event_repository.py

async def append_events_batch(
    session: AsyncSession,
    events: list[tuple[str, str, str]],  # (module, kind, payload_json)
) -> list[TaskEvent]:
    if not events:
        return []

    # 批量插入
    stmt = insert(TaskEvent).values([
        {"task_id": task_id, "module": m, "kind": k, "payload_json": p}
        for m, k, p in events
    ])
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

**使用**：

```python
# step_react_loop.py
batch = []
for tn, args in invocations:
    batch.append(("tool", "tool_call", json.dumps({...})))

    exec_out = await tool_registry.execute(tn, args)

    batch.append(("tool", "tool_result", json.dumps({...})))

# 一次性批量写入
if batch:
    await event_repository.append_events_batch(db, task_id, batch)
```

---

### 3.2 合并同阶段事件

**当前**：`step_start`, `tool_call`, `tool_result`, `step_end` 各自独立写入

**优化**：在同一事务中批量写入

```python
# step_executor.py

async def execute_step(db, task_id, step, ...):
    events = []

    # 收集所有事件
    events.append(("execution", "step_start", json.dumps({...})))

    for tn, args in invocations:
        events.append(("execution", "tool_call", json.dumps({...})))
        exec_out = await tool_registry.execute(tn, args)
        events.append(("execution", "tool_result", json.dumps({...})))

    events.append(("execution", "step_end", json.dumps({...})))

    # 批量写入
    await event_repository.append_events_batch(db, task_id, events)
```

---

## 四、SSE 推送优化

### 4.1 降低轮询间隔

**当前**：100ms

```python
# event_stream_service.py
_POLL_INTERVAL_SEC = 0.1   # 100ms
```

**优化**：50ms 或更低

```python
_POLL_INTERVAL_SEC = 0.05   # 50ms
```

### 4.2 事件通知机制（可选）

**问题**：轮询始终有最大延迟

**方案**：事件写入后主动通知 SSE

```python
# 使用 asyncio.Queue 作为通知队列
_event_queues: dict[str, asyncio.Queue] = {}

async def iter_task_event_sse(task_id, after_seq):
    queue = _event_queues.get(task_id) or asyncio.Queue()
    _event_queues[task_id] = queue

    while True:
        # 等待通知或超时
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_POLL_INTERVAL_SEC)
            yield format_sse(event)
        except asyncio.TimeoutError:
            # 超时检查终态
            if is_terminal(task_id):
                break

# 事件写入后立即通知
async def append_and_notify(db, task_id, event):
    await event_repository.append_event(db, task_id, ...)
    if task_id in _event_queues:
        _event_queues[task_id].put_nowait(event)
```

---

## 五、LLM 调用优化

### 5.1 减少 ReAct 轮次

**当前**：`max_react_rounds_per_step = 20`

**优化**：基于置信度提前终止

```python
async def run_step_react_loop(...):
    for round_num in range(max_rounds):
        msg = await ainvoke_with_retry(chat, messages, settings)
        data = parse_react_round_json(text)

        # 高置信度终答直接结束
        if fa and _high_confidence(fa):
            return ...

        # 轮次过多且有工具调用时强制终止
        if round_num >= 5 and not invocations:
            break
```

### 5.2 缓存重复工具描述

```python
# 全局工具描述缓存
_tool_description_cache: dict[str, str] = {}

def get_tool_description(tool_name: str) -> str:
    if tool_name not in _tool_description_cache:
        tool = builtin_lc_tools_by_name().get(tool_name)
        _tool_description_cache[tool_name] = tool.description
    return _tool_description_cache[tool_name]
```

### 5.3 规划器快速路径

**当前**：JSON 解析失败最多重试 3 次

**优化**：首次失败直接回退默认计划

```python
async def plan_steps_with_llm(chat_messages, settings):
    # 首次调用
    msg = await ainvoke_with_retry(chat, messages, settings)
    data = parse_llm_json_object(text)

    if data and _validate_steps(data):
        return _normalize_steps(data)

    # 首次失败即回退，不重试
    logger.warning("规划 LLM 解析失败，使用默认计划")
    return list(_DEFAULT_STEPS)
```

---

## 六、重试策略优化

### 6.1 LLM 重试退避

**当前**：429 错误 base=1.5s，最长 60s

```python
# 当前配置
openai_retry_base_delay_sec: float = 1.5
openai_retry_max_delay_sec: float = 60.0
```

**优化**：降低初始延迟，快速失败

```python
openai_retry_base_delay_sec: float = 0.5   # 降低到 0.5s
openai_retry_max_delay_sec: float = 10.0  # 降低到 10s
```

### 6.2 工具重试优化

**当前**：base=0.5s, max=8s

```python
# 当前
tool_retry_base_delay_sec: float = 0.5
tool_retry_max_delay_sec: float = 8.0
```

**优化**：更激进地重试

```python
tool_retry_base_delay_sec: float = 0.2   # 更短的初始延迟
tool_retry_max_delay_sec: float = 4.0    # 更短的最大延迟
max_tool_failure_attempts: int = 2       # 减少重试次数
```

---

## 七、配置优化汇总

```python
# backend/app/core/config.py

class Settings:
    # SSE 轮询
    sse_poll_interval_sec: float = 0.05  # 50ms（原 100ms）

    # LLM 重试（更快速失败）
    openai_retry_base_delay_sec: float = 0.5   # 1.5 → 0.5
    openai_retry_max_delay_sec: float = 10.0   # 60 → 10

    # 工具重试
    tool_retry_base_delay_sec: float = 0.2     # 0.5 → 0.2
    tool_retry_max_delay_sec: float = 4.0       # 8 → 4
    max_tool_failure_attempts: int = 2          # 3 → 2

    # ReAct 限制
    max_react_rounds_per_step: int = 10        # 20 → 10

    # 规划器（快速失败）
    planner_parse_max_attempts: int = 1         # 3 → 1
```

---

## 八、优化效果预估

### 8.1 优化前后对比

| 优化项 | 优化前 | 优化后 | 节省 |
|--------|--------|--------|------|
| SSE 轮询间隔 | 100ms | 50ms | 50ms |
| 工具并行执行 | 串行 ~600ms | 并行 ~300ms | ~300ms/步 |
| 批量 DB 写入 | 11 事务 ~165ms | 1 事务 ~30ms | ~135ms/步 |
| 快速失败 | 最多 3 次规划重试 | 1 次 | ~2s |
| 降低重试延迟 | base 1.5s | base 0.5s | ~2s (遇错误时) |
| ReAct 轮次 | 最多 20 | 最多 10 | ~2s/步 |

### 8.2 预期总延迟

**优化后典型路径**（2 步计划，每步 2 工具，无重试）：

| 阶段 | 优化后 |
|------|--------|
| POST /tasks | ~50ms |
| Planner LLM | ~2s |
| Actor 第 1 步 (并行工具) | ~2.5s |
| Actor 第 2 步 (并行工具) | ~2.5s |
| 总结 LLM | ~2s |
| Learner LLM | ~2s |
| **总计** | **~11s** |

**提升**：13-16s → ~11s，**提升约 20-30%**

---

## 九、实施优先级

| 优先级 | 优化项 | 工作量 | 风险 |
|--------|--------|--------|------|
| P0 | SSE 轮询降至 50ms | 5 分钟 | 低 |
| P0 | 批量 DB 事件写入 | 2-3 小时 | 中 |
| P1 | 工具并行执行 | 1-2 小时 | 中 |
| P1 | 降低重试延迟 | 5 分钟 | 低 |
| P1 | 规划器快速失败 | 30 分钟 | 低 |
| P2 | ReAct 轮次限制 | 30 分钟 | 低 |
| P2 | SSE 通知机制 | 4-6 小时 | 高 |

---

## 十、关键文件

| 文件 | 优化位置 |
|------|---------|
| `services/event_stream_service.py` | 第 21 行：轮询间隔 |
| `repositories/event_repository.py` | 第 9 行：批量写入 |
| `modules/execution/step_react_loop.py` | 第 126 行：并行工具 |
| `modules/execution/nodes.py` | 第 22 行：批量刷库 |
| `modules/planning/llm.py` | 第 84 行：快速失败 |
| `core/config.py` | 第 48-94 行：重试配置 |
