# ForgeAgent Agent 执行流程

## 一、整体架构

```
START → planner → actor → learner
                        ↓
              条件边: replan_requested?
                   ↙          ↘
               planner        END
```

---

## 二、Actor 节点

**文件**: `modules/execution/nodes.py`

### 2.1 核心流程

```python
async def actor_node(state: AgentState) -> dict:
    task_id = state["task_id"]
    plan_steps = state.get("plan_steps") or []
    tool_trace: list[dict] = []

    # 1. 遍历计划步骤执行
    for step in plan_steps:
        trace_row = await execute_plan_step_react(
            task_id,
            step,
            user_message=user_message_exec,
            prior_tool_trace=tool_trace,
            tools=exec_tools,
            settings=settings_exec,
            max_tool_tries=max_tool_tries,
            max_react_rounds=max_react_rounds,
        )
        tool_trace.append(trace_row)

    # 2. 生成面向用户的总结回复（流式）
    async for phase, delta in assistant_reply_stream_with_llm(...):
        await batcher.add(phase, delta)

    return {
        "outcome": "success",
        "summary": summary,
        "replan_requested": False,
        "actor_tool_trace": tool_trace,
    }
```

---

## 三、ReAct 循环详解

**文件**: `modules/execution/step_react_loop.py`

### 3.1 循环结构

```python
async def run_step_react_loop(...) -> tuple[bool, list[dict], str | None]:
    # 1. 首轮消息
    messages: list[BaseMessage] = [
        SystemMessage(content=sys_text),
        HumanMessage(content=initial),
    ]

    # 2. 步内循环
    while True:
        if round_num >= rounds:
            break

        # 调用 LLM
        msg = await ainvoke_with_retry(chat, messages, s)
        text = lc_message_text(msg)
        messages.append(AIMessage(content=text))

        # 解析 JSON
        data = parse_react_round_json(text)
        invocations = extract_tool_invocations(data)
        fa = pick_final_answer(data)

        if invocations:
            # 执行工具
            for tn, args in invocations:
                final_ok, last_exec, attempt_rows = await run_single_tool_with_retry(...)
                call_results.append({...})
                messages.append(HumanMessage(content="Observation:\n" + observation_block))
            continue

        if fa:
            step_final = fa
            break
```

### 3.2 LLM 输出格式

模型返回 JSON，结构示例：
```json
{
  "thought": "我需要先读取文件内容...",
  "actions": [
    {"tool": "read_file", "args": {"file_path": "/some/file.txt"}}
  ]
}
```
或直接给出最终答案：
```json
{
  "thought": "根据工具执行结果...",
  "final_answer": "任务已完成，文件内容是..."
}
```

### 3.3 循环结束条件

| 条件 | 说明 |
|------|------|
| `fa` (final_answer) 存在 | 模型直接返回答案 |
| `round_num >= max_rounds` | 达到轮次上限（默认 20） |
| Token 预算超限 | `total_tokens_used > token_budget` |
| 工具全部成功但无终答 | 触发 `try_react_closing_final_answer()` |

### 3.4 强制收口机制

```python
async def try_react_closing_final_answer(...):
    """在工具全部成功前提下，追加一轮争取 final_answer"""
    messages.append(HumanMessage(content=CLOSING_FINAL_NUDGE))
    msg = await ainvoke_with_retry(chat, messages, s)
    # 解析并返回 final_answer
```

---

## 四、Step ReAct System Prompt

**文件**: `modules/prompts/step_react.py`

```python
def build_step_react_system_prompt(tools: Sequence[ToolItem]) -> str:
    catalog = tools_catalog_for_prompt(tools)
    return f"""You are an execution agent.
    Inside the **current plan step only**, use a ReAct-style loop...

    ## Available tools
    {catalog}

    ## Output format
    - 调用工具：{{"thought":"...","action":"tool_name","action_input":{{...}}}}}
    - 直接回答：{{"thought":"...","final_answer":"完整回答"}}
    """
```

---

## 五、最终回复生成

**文件**: `modules/execution/llm_reply.py`

```python
async def assistant_reply_stream_with_llm(...) -> AsyncIterator[tuple[str, str]]:
    # 拼接上下文
    human_stream = (
        f"User question: {user_message}\n"
        f"Plan steps: {plan_text}\n"
        f"Tool execution results: {trace_text}"
    )

    # 流式生成，按相位拆分为 thinking / answer
    async for chunk in astream_with_retry(chat, messages, s):
        for phase, delta in splitter.feed(text):
            yield phase, delta
```

---

## 六、流式事件处理

### 6.1 SSE 事件类型

| Kind | 说明 |
|------|------|
| `step_start` | 步骤开始执行 |
| `llm_stream_delta` | LLM 流式输出增量 |
| `tool_call` | 工具调用 |
| `tool_result` | 工具执行结果 |
| `step_end` | 步骤执行结束 |

### 6.2 流式分割

**文件**: `modules/execution/stream_split.py`

```python
_OPEN_RE = re.compile(r"<think>", re.IGNORECASE)
_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)
```

最终 `summary` 格式：
```
<think>模型思考内容
</think>

用户可见的回答内容
```

---

## 七、完整执行流程图

```
planner_node
    │
    ▼
[plan_steps: [{"id":"1","title":"..."}, ...]]
    │
    ▼
for step in plan_steps:
    │
    ├─ execute_plan_step_react()
    │       │
    │       ▼
    │   run_step_react_loop()
    │       │
    │       ├── LLM: thought + actions/final_answer
    │       │
    │       ├── actions?
    │       │   │
    │       │   └── run_single_tool_with_retry()
    │       │           │
    │       │           ▼
    │       │       Observation → messages
    │       │           │
    │       │           └── 继续循环
    │       │
    │       └── final_answer? → 退出循环
    │
    ├─ 落库 step_start / step_end
    └─ 记录到 actor_tool_trace
    │
    ▼
assistant_reply_stream_with_llm()
    │
    ▼
learner_node
    │
    ▼
route_after_learner
    │
    ├── replan_requested=True → planner
    │
    └── replan_requested=False → END
```

---

## 八、关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `react_max_rounds` | 20 | 单步最大 ReAct 循环次数 |
| `react_max_tokens_per_step` | 8000 | 单步最大输出 token |
| `react_tool_observation_max_json_chars` | 12000 | 单条 Observation 最大字符 |
| `max_tool_tries` | 3 | 单工具最大重试次数 |

---

## 九、关键文件索引

| 文件 | 作用 |
|------|------|
| `modules/execution/nodes.py` | Actor 节点实现 |
| `modules/execution/step_react_loop.py` | ReAct 循环核心 |
| `modules/execution/step_executor.py` | 单步执行包装 |
| `modules/execution/tool_runner.py` | 工具执行+重试 |
| `modules/execution/llm_reply.py` | 流式总结回复 |
| `modules/execution/stream_split.py` | thinking/answer 分割 |
| `modules/prompts/step_react.py` | ReAct System Prompt |
