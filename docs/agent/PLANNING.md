# 规划模块

## Planner 节点

```python
async def planner_node(state: AgentState) -> dict:
    # 1. 加载会话历史
    messages = await session_context.load_chat_messages(...)

    # 2. 追加黑板笔记
    notes = state.get("blackboard_notes") or []
    if notes:
        messages.append(HumanMessage(content=bb))

    # 3. 调用 LLM 生成计划
    steps = await plan_steps_with_llm(messages, settings)

    return {"plan_steps": steps, "replan_count": ...}
```

## 计划结构

```json
{
  "steps": [
    {"id": "1", "title": "理解需求", "description": "..."},
    {"id": "2", "title": "分解任务", "description": "..."}
  ]
}
```

## 重规划

触发条件：
- Actor 请求重规划
- Learner LLM 反思建议重规划
- `replan_count < max_replan_attempts`
