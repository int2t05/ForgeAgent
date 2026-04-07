# 上下文管理

## Token 预算三层策略

| 层级 | 方法 | 精度 |
|------|------|------|
| 1 | Chat 模型内置计数 | 高 |
| 2 | tiktoken 精确计数 | 高 |
| 3 | 启发式估算 | 低 |

## 截断策略

1. 系统消息优先保留
2. 非系统消息自新向旧贪心装入
3. 若装不下，截断最旧消息

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

## 摘要压缩

触发条件：消息数 > 20

```
旧消息 ──► LLM 摘要 ──► [历史摘要] + 最近 10 条
```

## 配置

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `llm_context_window_tokens` | 204800 | 上下文窗口 |
| `llm_reserved_completion_tokens` | 8192 | 输出预留 |
| `llm_max_input_tokens` | ~196608 | 输入预算 |
| `llm_use_exact_token_count` | True | 精确计数 |
