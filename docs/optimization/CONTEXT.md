# 上下文管理优化

## 现有机制

| 模块 | 文件 | 功能 |
|------|------|------|
| 消息加载 | `session_context.py` | 从 DB 加载最近 32 条 |
| Token 估算 | `llm_context_budget.py` | tiktoken / 模型计数 |
| 截断策略 | `llm_context_budget.py` | 保留系统块，自新向旧填充 |
| 黑板记忆 | `session_blackboard.py` | 跨任务持久化 |

## 优化方案

### Tier 1: 精确 Token 计数

```python
from anthropic import Anthropic

class TokenCounter:
    def count(self, messages: list[dict]) -> int:
        return self._client.messages.count_tokens(
            model=self._model,
            messages=messages
        ).input_tokens
```

### Tier 2: 对话摘要压缩

```python
async def maybe_compress_chat_history(messages, settings):
    if len(messages) <= settings.session_summarize_when_over:
        return messages

    old = messages[:-settings.session_summary_keep_recent]
    recent = messages[-settings.session_summary_keep_recent:]

    # LLM 生成摘要
    summary = await llm.summarize(old)

    return [SystemMessage(content=f"[历史摘要]\n{summary}"), *recent]
```

### Tier 3: 结构化黑板

```sql
CREATE TABLE session_memories (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    category VARCHAR(50),  -- user_preference, context, fact
    content TEXT,
    importance INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 实施优先级

| 优先级 | 优化项 | 效果 |
|--------|--------|------|
| P0 | 精确 Token 计数 | 截断精度 95%+ |
| P0 | 智能截断策略 | 保留更多上下文 |
| P1 | 对话摘要压缩 | 长对话不丢历史 |
| P1 | 结构化黑板记忆 | 记忆可检索 |
| P2 | 跨会话长期记忆 | 跨会话偏好 |
