# ForgeAgent 上下文管理优化方案

## 一、当前状态

### 1.1 现有机制

| 模块 | 文件 | 说明 |
|------|------|------|
| 消息加载 | `memory/session_context.py` | 从 DB 加载最近 32 条消息 |
| Token 估算 | `memory/llm_context_budget.py` | tiktoken / 模型计数优先，附启发式回退 |
| 截断策略 | `memory/llm_context_budget.py` | 保留系统块；非系统从最新往前填充预算 |
| 黑板记忆 | `memory/session_blackboard.py` | 跨任务持久化，但容量有限 |

### 1.2 存在的问题

- Token 估算误差大（可能偏差 20-30%）
- 对话超长时直接截断，历史信息丢失
- 无摘要压缩机制
- 无长期记忆（跨会话）

---

## 二、优化方案

### 2.1 Tier 1: 精确 Token 计数（1-2 天）

**现状**：启发式估算

```python
# 当前 - 精度低
def estimate_messages_tokens(chat, messages) -> int:
    return len(content) // 3 + msgs * 4
```

**方案**：接入 Anthropic 精确计数

```python
# backend/app/modules/memory/token_counter.py

from anthropic import Anthropic

class TokenCounter:
    def __init__(self, model: str):
        self._client = Anthropic()
        self._model = model

    def count(self, messages: list[dict], system: str | None = None) -> int:
        params = {"model": self._model, "messages": messages}
        if system:
            params["system"] = system
        return self._client.messages.count_tokens(**params).input_tokens

# 使用
counter = TokenCounter(settings.openai_model)
tokens = counter.count([{"role": "user", "content": "hello"}])
```

**预期效果**：截断精度提升，误差 <5%

---

### 2.2 Tier 1: 简化截断策略（1 天）

**现状**：先丢历史再截断首条

**方案**：保留最近 N 条 + 系统提示，始终完整

```python
# backend/app/modules/memory/llm_context_budget.py

def truncate_to_budget(messages: list[BaseMessage], max_tokens: int) -> list[BaseMessage]:
    """智能截断：保留最新消息，截断最旧消息"""
    # 1. 系统消息始终保留
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    others = [m for m in messages if not isinstance(m, SystemMessage)]

    # 2. 从最新开始保留，直到 token 超限
    result = system_msgs.copy()
    for msg in reversed(others):
        test = result + [msg]
        if counter.count(test) <= max_tokens:
            result.append(msg)
        else:
            break

    # 3. 保持时间顺序
    return list(reversed(result))
```

---

### 2.3 Tier 2: 对话摘要压缩（3-5 天）

**现状**：超长直接丢弃（截断层仍会裁尾部，摘要可减少先验丢失）

**已实现**：`backend/app/modules/memory/conversation_summary.py` 的 ``maybe_compress_chat_history``，在 ``SessionLLMContextManager.load_chat_messages`` 中于入库窗口加载后调用。

**方案（参考）**：引入摘要机制

```python
# 参考形态（实际见 conversation_summary.py）

async def summarize_old_messages(messages: list[BaseMessage], max_keep: int = 10) -> tuple[list[BaseMessage], str]:
    """将旧消息压缩为摘要"""

    if len(messages) <= max_keep:
        return messages, ""

    old = messages[:-max_keep]
    recent = messages[-max_keep:]

    # LLM 生成摘要
    summary_prompt = f"""请总结以下对话的要点（不超过 100 字）：

{chr(10).join([f"{m.type}: {m.content[:200]}" for m in old])}"""

    response = await llm.ainvoke([HumanMessage(content=summary_prompt)])
    summary = response.content if hasattr(response, 'content') else str(response)

    # 用摘要替换旧消息
    summarized = [SystemMessage(content=f"[对话摘要] {summary}")]
    return summarized + recent, summary
```

**触发条件**：消息数 > 阈值（如 20 条）

---

### 2.4 Tier 2: 黑板记忆增强（2-3 天）

**现状**：`sessions.blackboard_notes_json` 仅存储字符串列表

**方案**：结构化记忆 + 语义检索

```sql
-- 新增表
CREATE TABLE session_memories (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    category VARCHAR(50),        -- "user_preference", "context", "fact"
    content TEXT,
    embedding VECTOR(1536),     -- 可选：存储向量
    importance INT DEFAULT 1,   -- 1-5 星
    created_at TIMESTAMP DEFAULT NOW()
);
```

```python
# backend/app/memory/structured_memory.py

class StructuredMemory:
    async def store(self, session_id: int, category: str, content: str, importance: int = 3):
        """存储结构化记忆"""
        await db.execute(
            insert(session_memories).values(
                session_id=session_id,
                category=category,
                content=content,
                importance=importance
            )
        )

    async def retrieve(self, session_id: int, categories: list[str] | None = None, limit: int = 5) -> list[str]:
        """检索相关记忆"""
        query = select(session_memories).where(session_memories.c.session_id == session_id)
        if categories:
            query = query.where(session_memories.c.category.in_(categories))

        query = query.order_by(session_memories.c.importance.desc()).limit(limit)
        rows = await db.execute(query)

        return [f"[{r.category}] {r.content}" for r in rows]
```

**使用**：Planner 节点加载黑板时，合并结构化记忆

---

### 2.5 Tier 3: 跨会话长期记忆（可选，5-7 天）

**需求**：记住用户偏好、常用工作模式等

```python
# backend/app/memory/user_memory.py

class UserMemoryStore:
    """用户级长期记忆"""

    async def remember(self, user_id: str, key: str, value: str):
        """记忆一条用户信息"""
        await self._store.put(("user", user_id, key), {"data": value})

    async def recall(self, user_id: str, key: str) -> str | None:
        """回忆用户信息"""
        result = await self._store.get(("user", user_id, key))
        return result["data"] if result else None

    async def search(self, user_id: str, query: str, limit: int = 3) -> list[str]:
        """语义搜索用户记忆"""
        namespace = ("user_memories", user_id)
        results = await self._store.search(namespace, query=query, limit=limit)
        return [r.value["data"] for r in results]
```

**在 System Prompt 中注入**：

```python
def build_system_prompt(user_memories: list[str] | None = None) -> str:
    prompt = BASE_SYSTEM_PROMPT
    if user_memories:
        prompt += "\n\n【用户偏好】\n" + "\n".join(user_memories)
    return prompt
```

---

## 三、实施优先级

| 优先级 | 优化项 | 工作量 | 效果 |
|--------|--------|--------|------|
| P0 | 精确 Token 计数 | 1-2 天 | 截断准确 |
| P0 | 智能截断策略 | 1 天 | 保留更多上下文 |
| P1 | 对话摘要压缩 | 3-5 天 | 长对话不丢历史 |
| P1 | 结构化黑板记忆 | 2-3 天 | 记忆可检索 |
| P2 | 跨会话长期记忆 | 5-7 天 | 跨会话偏好 |

---

## 四、关键配置

```python
# config.py

class Settings:
    # Token 计数
    use_exact_token_count: bool = True

    # 摘要配置
    enable_summarization: bool = True
    summarize_after_messages: int = 20      # 超过此数量触发摘要
    summary_max_tokens: int = 150

    # 黑板配置
    blackboard_max_notes: int = 20
    blackboard_importance_threshold: int = 3  # 只保留重要性 >= 3 的记忆
```

---

## 五、总结

| 层级 | 方案 | 收益 |
|------|------|------|
| **Token 计数** | 启发式 → API 精确计数 | 精度 95%+ |
| **截断策略** | 先丢先截 → 保留最新 | 上下文更合理 |
| **摘要压缩** | 直接丢弃 → LLM 摘要 | 历史不丢失 |
| **黑板记忆** | 字符串列表 → 结构化 | 可筛选可检索 |
| **长期记忆** | 无 → 用户级 Store | 跨会话偏好 |
