# 记忆模块

## 会话上下文

```python
class SessionLLMContextManager:
    async def load_chat_messages(self, db, session_id, fallback_content):
        # 从 DB 加载最近 N 条消息
        rows = await message_repository.list_recent_messages(...)
        # ORM → LangChain 消息
        msgs = session_messages_to_chat_messages(rows)
        # 摘要压缩
        return await maybe_compress_chat_history(msgs, settings)
```

## 黑板记忆

跨任务共享的反思笔记：

```python
# 写入
notes = list(state.get("blackboard_notes") or [])
notes.append(reflection_text)
notes = cap_blackboard_notes(notes, max_notes=64)

# 读取
notes = state.get("blackboard_notes") or []
tail = notes[-10:]  # 只取最后 10 条
```

## Learner 反思

```python
async def learner_node(state: AgentState) -> dict:
    # 1. 生成反思
    reflection = await llm.generate_reflection(
        tool_trace=state["actor_tool_trace"],
        outcome=state["outcome"]
    )

    # 2. 追加到黑板
    notes = list(state["blackboard_notes"])
    notes.append(reflection["text"])

    # 3. 决定是否重规划
    wants_replan = reflection.get("request_replan")

    return {"blackboard_notes": notes, "replan_requested": wants_replan}
```

## 配置

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `session_memory_max_messages` | 32 | 消息加载上限 |
| `session_blackboard_max_notes` | 64 | 黑板最大条数 |
| `session_conversation_summary_enabled` | True | 启用摘要 |
| `session_summarize_when_over` | 20 | 触发摘要阈值 |
