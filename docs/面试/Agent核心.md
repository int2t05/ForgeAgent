# Agent 核心模块面试题

## 1. Plan-Act-Learn 详解

### Q: 三大节点职责？

| 节点 | 输入 | 输出 | 核心逻辑 |
|------|------|------|----------|
| **Planner** | user_message, blackboard | plan_steps | LLM 生成计划 JSON |
| **Actor** | plan_steps, user_message | summary, tool_trace | ReAct 循环执行 |
| **Learner** | tool_trace, outcome | blackboard_notes | LLM 生成反思 |

### Q: Planner 如何生成计划？

```python
async def planner_node(state: AgentState) -> dict:
    # 1. 加载会话历史
    messages = await session_context.load_chat_messages(...)

    # 2. 追加黑板（最后 10 条）
    notes = state.get("blackboard_notes") or []
    if notes:
        bb = "\n".join(notes[-10:])
        messages.append(HumanMessage(content=bb))

    # 3. 调用 LLM 生成计划
    steps = await plan_steps_with_llm(messages, settings)

    return {"plan_steps": steps}
```

### Q: 计划 JSON 格式？

```json
{
  "steps": [
    {
      "id": "1",
      "title": "理解需求",
      "description": "分析用户输入和上下文"
    },
    {
      "id": "2",
      "title": "实现代码",
      "description": "编写并测试代码"
    }
  ]
}
```

**注意**：计划是抽象步骤，不含工具！

---

## 2. ReAct 循环

### Q: ReAct 循环流程？

```python
async def run_step_react_loop(...) -> tuple[bool, list, str]:
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_prompt)
    ]

    while True:
        # 1. LLM 生成 thought + action/final_answer
        msg = await ainvoke_with_retry(chat, messages, settings)
        text = lc_message_text(msg)
        messages.append(AIMessage(content=text))

        # 2. 解析 JSON
        data = parse_react_round_json(text)
        invocations = extract_tool_invocations(data)
        fa = pick_final_answer(data)

        # 3. 有工具调用？
        if invocations:
            for tn, args in invocations:
                result = await run_single_tool_with_retry(...)
                messages.append(HumanMessage(content=result))
            continue

        # 4. 有最终答案？
        if fa:
            return fa
```

### Q: LLM 输出格式？

```json
{
  "thought": "用户想要计算阶乘，我需要...",
  "action": "python_repl",
  "action_input": {"code": "def factorial(n): return 1 if n <= 1 else n * factorial(n-1)"}
}

{
  "thought": "已完成阶乘函数",
  "final_answer": "阶乘函数已实现..."
}
```

---

## 3. 工具执行

### Q: 工具执行带重试？

```python
async def run_single_tool_with_retry(task_id, tool_name, args, max_tries):
    for attempt in range(1, max_tries + 1):
        # 1. 熔断检查
        breaker.before_call()

        # 2. 执行工具
        result = await tool_registry.execute(tool_name, args)

        if result["ok"]:
            breaker.record_success()
            return result

        # 3. 失败：熔断记录 + 指数退避
        breaker.record_failure()
        if attempt < max_tries:
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            await asyncio.sleep(delay)
```

### Q: 指数退避公式？

```
delay = min(max_delay, base_delay * 2^(attempt-1) * jitter)
jitter ∈ [0.5, 1.0)
```

示例（base=0.5s, max=10s）：
- attempt 1: 0.5 * 1 * 0.75 ≈ 0.375s
- attempt 2: 0.5 * 2 * 0.8 ≈ 0.8s
- attempt 3: 0.5 * 4 * 0.6 ≈ 1.2s

---

## 4. 重规划机制

### Q: 何时触发重规划？

```python
# Learner 节点
wants_replan = (
    not failed  # 非失败
    and can_replan  # 还有重规划次数
    and (actor_replan or llm_request_replan)  # 有人请求
)
```

### Q: 重规划 vs 重新执行？

| 场景 | 处理 |
|------|------|
| 步骤执行失败 | 当前步重试 |
| 步骤执行成功但效果不佳 | 重规划（回到 Planner） |
| 计划本身有问题 | 重规划 |
| 任务失败 | 结束 |

---

## 5. 记忆系统

### Q: Session Memory 加载流程？

```python
async def load_chat_messages(db, session_id):
    # 1. 从 DB 加载最近 32 条
    rows = await message_repository.list_recent_messages(
        db, session_id, limit=32
    )

    # 2. ORM → LangChain 消息
    msgs = session_messages_to_chat_messages(rows)

    # 3. 触发摘要压缩（>20 条）
    return await maybe_compress_chat_history(msgs, settings)
```

### Q: 何时触发摘要？

```python
if len(messages) > settings.session_summarize_when_over:
    # 旧消息 → LLM 摘要
    # [历史摘要] + 最近 10 条
```

### Q: 黑板 vs 记忆区别？

| 概念 | 内容 | 生命周期 |
|------|------|----------|
| **Session Memory** | 会话历史消息 | 会话内 |
| **Blackboard** | 反思要点 | 跨任务 |

---

## 6. Token 管理

### Q: Token 截断策略？

```
1. 系统消息优先保留
2. 非系统消息自新向旧贪心装入
3. 若装不下，截断最旧消息
```

```python
def truncate_chat_messages_to_budget(messages, max_tokens):
    system = [m for m in messages if isinstance(m, SystemMessage)]
    others = [m for m in messages if not isinstance(m, SystemMessage)]

    result = system.copy()
    for msg in reversed(others):
        if estimate_tokens(result + [msg]) <= max_tokens:
            result.append(msg)
        else:
            break
    return result
```

### Q: Token 计数优先级？

| 优先级 | 方法 | 精度 |
|--------|------|------|
| 1 | Chat 模型内置 | 最高 |
| 2 | tiktoken | 高 |
| 3 | 启发式估算 | 低 |

---

## 7. 状态机

### Q: LangGraph 如何定义工作流？

```python
def build_agent_graph():
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("planner", planner_node)
    builder.add_node("actor", actor_node)
    builder.add_node("learner", learner_node)

    # 添加边
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "actor")
    builder.add_edge("actor", "learner")

    # 条件边
    builder.add_conditional_edges(
        "learner",
        route_after_learner,
        {"planner": "planner", "done": END}
    )

    return builder.compile()
```

### Q: route_after_learner 实现？

```python
def route_after_learner(state: AgentState) -> Literal["planner", "done"]:
    if state.get("outcome") == "failed":
        return "done"
    if state.get("replan_requested"):
        return "planner"
    return "done"
```
