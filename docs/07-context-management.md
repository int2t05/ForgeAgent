# ForgeAgent 上下文管理流程

## 一、核心文件

| 功能 | 文件 |
|------|------|
| 会话上下文加载 | `memory/session_context.py` |
| Token 预算与截断 | `memory/llm_context_budget.py` |
| 对话历史摘要压缩 | `memory/conversation_summary.py` |
| Token 精确计数 | `memory/token_counter.py` |
| Session 黑板 | `memory/session_blackboard.py` |

---

## 二、消息加载流程

### 2.1 入口函数

**文件**: `memory/session_context.py`

```python
async def load_chat_messages(
    self,
    db: AsyncSession,
    *,
    session_id: str,
    fallback_user_content: str,
    settings: Settings | None = None,
) -> list[BaseMessage]:
    s = settings or get_settings()

    # 1. 从数据库加载最近消息
    rows = await message_repository.list_recent_messages(
        db, session_id, limit=self._max_messages
    )

    if not rows:
        return [HumanMessage(content=fallback_user_content)]

    # 2. ORM → LangChain 消息
    msgs = session_messages_to_chat_messages(rows)

    # 3. 可选的摘要压缩
    return await maybe_compress_chat_history(msgs, s)
```

### 2.2 SQL 查询

```python
# message_repository.py
async def list_recent_messages(session, session_id, *, limit):
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.id.desc())  # 倒序
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()  # 转为正序
    return rows
```

### 2.3 消息类型转换

```python
_ROLE_MAP = {
    "user": HumanMessage,
    "assistant": AIMessage,
}

def session_messages_to_chat_messages(rows):
    for row in rows:
        role = (row.role or "").strip().lower()
        # system 角色转为 HumanMessage 前缀
        if role == "system":
            out.append(HumanMessage(content=f"[会话 system]\n{row.content}"))
            continue
        cls = _ROLE_MAP.get(role, HumanMessage)
        out.append(cls(content=row.content))
    return out
```

---

## 三、Token 计数三层策略

**文件**: `memory/llm_context_budget.py`

### 3.1 计数入口

```python
def estimate_messages_tokens(chat, messages) -> int:
    # 1. 优先使用 Chat 模型内置计数
    if chat is not None:
        getter = getattr(chat, "get_num_tokens_from_messages", None)
        if callable(getter):
            try:
                return int(getter(msgs))
            except Exception:
                pass

    # 2. 其次使用 tiktoken 精确计数
    if get_settings().llm_use_exact_token_count:
        try:
            return count_messages_tokens(msgs, model=_model_name_for_token_count(chat))
        except Exception:
            pass

    # 3. 最后用启发式
    return _heuristic_messages_tokens(msgs)
```

### 3.2 Tiktoken 精确计数

```python
# memory/token_counter.py
def count_messages_tokens(messages: list[BaseMessage], *, model: str | None) -> int:
    enc = encoding_for_chat_model(model)
    total = 0
    for msg in messages:
        total += _TOKENS_PER_MESSAGE  # 4
        role = _role_for_message(msg)
        total += len(enc.encode(role))
        total += len(enc.encode(message_content_text(msg.content)))
    total += _REPLY_PRIMING_TOKENS  # 3
    return total
```

---

## 四、Token 截断策略

### 4.1 截断主函数

```python
def truncate_chat_messages_to_budget(chat, messages, *, max_input_tokens) -> list[BaseMessage]:
    budget = max(64, int(max_input_tokens))
    before = estimate_messages_tokens(chat, msgs)

    if before <= budget:
        return msgs  # 未超预算

    # 1. 拆分系统消息与其余角色消息
    sys_list = [m for m in msgs if isinstance(m, SystemMessage)]
    others = [m for m in msgs if not isinstance(m, SystemMessage)]

    # 2. 系统消息优先压缩
    _shrink_system_list(chat, sys_list, budget, len(sys_list))

    # 3. 自新向旧贪心装入非系统消息
    kept_rev = []
    for msg in reversed(others):
        trial = sys_list + list(reversed(kept_rev + [msg]))
        if estimate_messages_tokens(chat, trial) <= budget:
            kept_rev.append(msg)
        else:
            break

    # 4. 若装不下则截断最旧那条
    if kept_rev:
        out = sys_list + list(reversed(kept_rev))
    else:
        room = max(32, budget - estimate_messages_tokens(chat, sys_list))
        out = sys_list + [_truncate_one_message(chat, others[-1], room)]

    return out
```

### 4.2 单条消息截断（二分查找）

```python
def _truncate_one_message(chat, msg, max_tokens) -> BaseMessage:
    text = message_content_text(msg.content)
    # 二分查找找到最大可容纳文本长度
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(chat, text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return _replace_message_content(msg, text[:lo] + "\n\n[... 已省略部分内容 ...]")
```

---

## 五、对话摘要压缩

**文件**: `memory/conversation_summary.py`

### 5.1 触发条件

```python
async def maybe_compress_chat_history(messages, settings):
    if not settings.session_conversation_summary_enabled:
        return messages

    thr = int(settings.session_summarize_when_over)  # 默认 20
    if len(messages) <= thr:
        return messages

    keep_n = min(int(settings.session_summary_keep_recent), len(messages) - 1)
    old = messages[:-keep_n]
    recent = messages[-keep_n:]
    # ...
```

### 5.2 摘要生成

```python
    # 构建摘要提示
    lines = []
    for m in old:
        role = getattr(m, "type", None) or "message"
        snippet = message_content_text(m.content)[:line_cap]
        lines.append(f"{role}: {snippet}")

    body = "\n".join(lines)
    prompt = f"请用不超过 {ans_cap} 字的中文概括要点：\n\n{body}"

    # 调用 LLM 生成摘要
    chat = build_chat_model(settings)
    resp = await ainvoke_with_retry(chat, [HumanMessage(content=prompt)], settings)
    summary = getattr(resp, "content", "")

    # 组合：摘要消息 + 保留的最近消息
    head = HumanMessage(content=f"[历史对话摘要]\n{summary}")
    return [head, *recent]
```

---

## 六、Token 预算配置

**文件**: `core/config.py`

```python
# 上下文窗口总量
llm_context_window_tokens: int = 204_800
# 为输出预留的 token
llm_reserved_completion_tokens: int = 8192

@property
def llm_max_input_tokens(self) -> int:
    # 应用层实际输入预算 = 窗口 - 预留
    return max(256, w - r)  # 默认约 196_608
```

---

## 七、完整上下文流程图

```
用户输入 + Session ID
       │
       ▼
SessionLLMContextManager.load_chat_messages()
       │
       ├──► message_repository.list_recent_messages()
       │         └── SQL: ORDER BY id DESC LIMIT → reverse()
       │
       ├──► session_messages_to_chat_messages()
       │         └── ORM Message → LangChain BaseMessage
       │
       ├──► maybe_compress_chat_history()
       │         ├── 消息条数 > 20?
       │         ├── 旧消息 → LLM 摘要
       │         └── [历史摘要] + 最近 10 条
       │
       ▼
    [消息列表]
       │
       ▼  追加 System Prompt + 黑板
    [SystemMessage, ...历史消息, HumanMessage(黑板)]
       │
       ▼  调用 LLM 前
truncate_chat_messages_to_budget()
       ├── 估算总 token
       ├── 超预算?
       │   ├── 系统消息: 删前段 → 截断末条
       │   └── 非系统消息: 自新向旧贪心装入
       │
       ▼
    [截断后消息] → ainvoke_with_retry() → LLM
```

---

## 八、黑板注入流程

Planner 节点在调用规划 LLM 前，追加黑板到消息末尾：

```python
# modules/planning/nodes.py
notes = state.get("blackboard_notes") or []
if notes:
    tail = notes[-10:]
    bb = "【共享黑板·来自 Learner 的要点】\n" + "\n".join(tail)
    chat_messages = [*chat_messages, HumanMessage(content=bb)]
```

---

## 九、关键配置汇总

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `session_memory_max_messages` | 32 | 消息加载条数上限 |
| `llm_context_window_tokens` | 204800 | 模型总上下文窗口 |
| `llm_reserved_completion_tokens` | 8192 | 为输出预留 token |
| `llm_max_input_tokens` | ~196608 | 应用层输入预算 |
| `session_conversation_summary_enabled` | True | 是否启用摘要压缩 |
| `session_summarize_when_over` | 20 | 触发摘要的条数阈值 |
| `session_summary_keep_recent` | 10 | 摘要后保留的最近条数 |
| `llm_use_exact_token_count` | True | 是否使用 tiktoken 精确计数 |
| `react_tool_observation_max_json_chars` | 12000 | 单条 Observation 最大字符 |
