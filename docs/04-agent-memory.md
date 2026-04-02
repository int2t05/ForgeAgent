# ForgeAgent Agent 记忆流程

## 一、整体架构

记忆系统包含三个核心组件：

| 组件 | 文件 | 作用 |
|------|------|------|
| SessionContext | `memory/session_context.py` | 加载会话消息历史 |
| SessionBlackboard | `memory/session_blackboard.py` | 跨任务共享反思 |
| LearnerNode | `memory/learner_node.py` | 生成反思要点 |

---

## 二、会话上下文加载

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

### 2.2 消息转换

```python
_ROLE_MAP = {
    "user": HumanMessage,
    "human": HumanMessage,
    "assistant": AIMessage,
    "ai": AIMessage,
}

def session_messages_to_chat_messages(rows):
    out = []
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

## 三、黑板记忆管理

### 3.1 核心概念

黑板是**会话级别**的共享存储，持久化到 `sessions.blackboard_notes_json` 字段。

### 3.2 读取黑板

**文件**: `memory/session_blackboard.py`

```python
async def read_session_blackboard(db: AsyncSession, session_id: str) -> list[str]:
    row = await session_repository.get_session_by_id(db, session_id)
    return decode_blackboard_json(row.blackboard_notes_json) if row else []
```

### 3.3 写入黑板

```python
async def write_session_blackboard(
    db: AsyncSession,
    session_id: str,
    notes: list[str],
    *,
    max_notes: int,
):
    row = await session_repository.get_session_by_id(db, session_id)
    if row is None:
        return
    row.blackboard_notes_json = encode_blackboard_json(notes, max_notes)
```

### 3.4 黑板上限截断

```python
def cap_blackboard_notes(notes: list[str], max_notes: int) -> list[str]:
    m = max(1, int(max_notes))
    return notes[-m:] if len(notes) > m else notes
```

---

## 四、Learner 反思生成

### 4.1 触发时机

Learner 节点在 Actor 节点之后执行：

```
builder.add_edge("actor", "learner")
```

### 4.2 反思生成流程

**文件**: `memory/learner_node.py`

```python
async def learner_node(state: AgentState) -> dict:
    # 1. 检查是否可重规划
    max_r = max(0, int(state.get("max_replan_attempts") or 0))
    replan_count = int(state.get("replan_count") or 0)
    can_replan = replan_count < max_r
    failed = state.get("outcome") == "failed"
    actor_replan = bool(state.get("replan_requested"))

    # 2. LLM 生成结构化反思
    if is_llm_configured(settings) and not failed:
        messages = [
            SystemMessage(content=LEARNER_REFLECTION_SYSTEM),
            HumanMessage(content="【本回合执行材料】\n" + user_block),
        ]
        for attempt in range(max_rounds):
            msg = await ainvoke_with_retry(chat, messages, settings)
            data = parse_llm_json_object(text)
            if data and isinstance(data.get("reflection"), str):
                reflection_text = data["reflection"].strip()
                llm_request_replan = bool(data.get("request_replan"))
                break

    # 3. 回退合成（无 LLM 时）
    if not reflection_text:
        reflection_text = "\n".join(_synthesize_lesson_lines(state))

    # 4. 追加到黑板
    notes = list(state.get("blackboard_notes") or [])
    notes.append(reflection_text)
    notes = cap_blackboard_notes(notes, settings.session_blackboard_max_notes)

    # 5. 写反思事件
    await event_repository.append_event(db, task_id, "memory", "reflection", ...)

    # 6. 合并重规划意图
    wants_replan = (not failed) and can_replan and (actor_replan or llm_request_replan)

    return {
        "blackboard_notes": notes,
        "actor_tool_trace": [],
        "replan_requested": wants_replan,
    }
```

### 4.3 回退合成

```python
def _synthesize_lesson_lines(state: AgentState) -> list[str]:
    lines = []
    for row in state.get("actor_tool_trace") or []:
        if ok_c:
            lines.append(f"步骤 {sid} ({title})：工具 {tname} 调用成功。")
        else:
            lines.append(f"步骤 {sid} ({title})：工具 {tname} 未成功。")
    if state.get("outcome") == "success":
        lines.append("本回合执行成功。")
    elif state.get("outcome") == "failed":
        lines.append(f"本回合失败：{error_msg}")
    return lines
```

---

## 五、反思 Prompt

**文件**: `modules/prompts/learner_reflection.py`

```
You are the **Learner** module: short self-reflection after one agent turn.

## Inputs
{"reflection":"…","request_replan":false,"rationale":"…"}

## Task
1. Summarize reusable lessons, pitfalls, and corrections for the shared blackboard.
2. Decide if planning should run again (`request_replan`).

## Constraints
- If outcome is **failure**, `request_replan` must be **false**.
- If remaining replan cycles = 0, `request_replan` must be **false**.
```

---

## 六、记忆生命周期

```
[任务启动] → load_blackboard_seed(session_id)
                    │
                    ▼
[初始化 AgentState] → blackboard_notes = seed_notes
                    │
                    ▼
[Planner 节点]
  └─ 追加黑板最后10条 → HumanMessage → 传给规划 LLM
                    │
                    ▼
[Actor 节点]
  └─ 执行工具，累积 actor_tool_trace
                    │
                    ▼
[Learner 节点]
  ├─ LLM 生成反思 JSON (reflection + request_replan)
  ├─ 追加到 blackboard_notes
  └─ 决定是否重规划
                    │
                    ▼
[任务结束] → flush_blackboard_from_graph_checkpoint()
                    │
                    ▼
        sessions.blackboard_notes_json
                    │
                    ▼
            [下一任务继承]
```

---

## 七、节点间数据流

| 节点 | 读取 | 写入 |
|------|------|------|
| **Planner** | `blackboard_notes` | `plan_steps`, `replan_count` |
| **Actor** | `plan_steps`, `user_message` | `summary`, `actor_tool_trace`, `outcome` |
| **Learner** | `blackboard_notes`, `actor_tool_trace` | `blackboard_notes`(追加), `replan_requested` |

---

## 八、关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `session_memory_max_messages` | 32 | 消息加载条数上限 |
| `session_blackboard_max_notes` | 64 | 黑板最大条数 |
| `session_conversation_summary_enabled` | True | 是否启用摘要压缩 |
| `session_summarize_when_over` | 20 | 触发摘要的条数阈值 |
| `session_summary_keep_recent` | 10 | 摘要后保留的最近条数 |
