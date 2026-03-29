# ForgeAgent：LangGraph 最小 Plan-and-Execute（阶段4）

## 场景

单任务内：**先规划 → 再执行 →（可选）重规划**，并把过程写入 `task_events` 与 `tasks.plan_version`，终态写回 `tasks.status`。

## 依赖（版本以 `backend/pyproject.toml` 为准）

- `langgraph`：状态图、`START/END`、条件边、`compile()` / `ainvoke`
- `langchain-core`：与后续接 LLM 扩展对齐（本阶段规划节点可为确定性逻辑）

## 伪代码：图结构

```text
builder = StateGraph(AgentState)
builder.add_node("planner", planner_node)       # async: 写 plan_created
builder.add_node("executor", executor_node)     # async: step_start 循环
builder.add_node("replan_record", replan_record_node)  # async: plan_version++, kind=replan

builder.add_edge(START, "planner")
builder.add_edge("planner", "executor")
builder.add_conditional_edges(
    "executor",
    route_after_executor,
    {"replan": "replan_record", "done": END},
)
builder.add_edge("replan_record", "planner")

app = builder.compile()
result = await app.ainvoke(initial_state)
```

## 伪代码：节点内访问数据库（FastAPI 后台任务）

```text
# 勿在 HTTP 请求的 AsyncSession 里跑图；与阶段2 一样用 asyncio.create_task + 独立会话

async def planner_node(state):
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await append_event(db, state.task_id, "planning", "plan_created", payload_json)
    return {"plan_steps": steps, "current_step_index": 0}
```

## 伪代码：重规划边界

```text
# Settings.max_replan_attempts == N：最多记录 N 次「从 executor 因需重规划而进入 replan_record」
# force_replan_budget：将「测试令牌」收敛为可消费次数，避免每轮 planner 后仍在同一 user_message 上重复触发
if force_replan_budget > 0 and replan_count < max:
    return {"replan_requested": True, "force_replan_budget": budget - 1}
if force_replan_budget > 0 and replan_count >= max:
    return {"outcome": "failed", "error_message": "超过最大重规划次数"}
```

## 测试约定

- 强制重规划令牌：`__FORCE_REPLAN__` → 初始 `force_replan_budget=1`（仅用于自动化/本地，不接 LLM）
- 环境变量：`MAX_REPLAN_ATTEMPTS` 覆盖默认上限
