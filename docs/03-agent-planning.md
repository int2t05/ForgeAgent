# ForgeAgent Agent 规划流程

## 一、整体架构

三节点工作流中的规划节点：

```
START → planner → actor → learner
              ↑                │
              └── replan ──────┘
```

---

## 二、计划数据结构

### 2.1 AgentState 中的计划字段

```python
class AgentState(TypedDict, total=False):
    plan_steps: list[dict[str, Any]]   # 计划步骤列表
    current_step_index: int            # 当前步骤索引
    replan_count: int                 # 已重规划次数
    replan_requested: bool            # 是否请求重规划
```

### 2.2 步骤结构

```python
{
    "id": "1",                              # 步骤 ID
    "title": "理解用户输入与上下文",          # 标题（必须，简体中文）
    "description": "澄清目标、约束与已知事实", # 可选描述
    "expected_output": "..."                 # 可选期望输出
}
```

**关键约束**：步骤是目标级抽象描述，**不含任何工具相关字段**。

---

## 三、Planner 节点

**文件**: `backend/app/modules/planning/nodes.py`

### 3.1 核心流程

```python
async def planner_node(state: AgentState) -> dict:
    task_id = state["task_id"]
    session_id = state.get("session_id") or ""

    # 1. 若请求重规划 → 递增计划版本
    if state.get("replan_requested"):
        new_version = await task_repository.bump_plan_version(db, task_id)
        await event_repository.append_event(db, task_id, "planning", "replan", ...)
        out["replan_count"] = next_count
        out["replan_requested"] = False

    # 2. 加载会话消息历史
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    chat_messages = await mgr.load_chat_messages(db, session_id, ...)

    # 3. 追加黑板笔记到消息末尾
    notes = state.get("blackboard_notes") or []
    if notes:
        tail = notes[-10:]
        bb = "【共享黑板·来自 Learner 的要点】\n" + "\n".join(tail)
        chat_messages = [*chat_messages, HumanMessage(content=bb)]

    # 4. 调用 LLM 生成计划
    steps = await plan_steps_with_llm(chat_messages, settings)

    # 5. 写 plan_created 事件
    await event_repository.append_event(db, task_id, "planning", "plan_created", ...)

    return {
        "plan_steps": steps,
        "current_step_index": 0,
        "replan_count": next_count,
    }
```

### 3.2 计划生成 LLM 调用

**文件**: `backend/app/modules/planning/llm.py`

```python
async def plan_steps_with_llm(chat_messages, settings):
    # 1. LLM 未配置时返回默认两步计划
    if not is_llm_configured(s):
        return list(_DEFAULT_STEPS)

    # 2. 构造消息
    messages = [SystemMessage(content=sys), *list(chat_messages)]

    # 3. 最多 max_rounds 轮解析重试
    for attempt in range(max_rounds):
        msg = await ainvoke_with_retry(chat, messages, settings)
        data = parse_llm_json_object(text)
        normalized = _normalize_steps(data)

        if normalized:
            return normalized

        # 解析失败 → 附上纠偏提示继续重试
        messages.append(msg)
        messages.append(HumanMessage(content=_PLANNER_PARSE_RETRY_USER_HINT))

    return list(_DEFAULT_STEPS)
```

### 3.3 步骤规范化

```python
_FORBIDDEN_PLAN_KEYS = frozenset({
    "tool", "args", "tool_name", "function",
    "function_call", "action",
})

def _normalize_steps(data):
    steps = data.get("steps")
    # 验证 steps 是非空列表
    for item in steps:
        # 剔除任何工具相关键
        leaked = _FORBIDDEN_PLAN_KEYS.intersection(item.keys())
        # 提取 id, title, description
        row = {"id": sid, "title": title.strip()}
        for meta_key in ("goal", "description", "expected_output"):
            if mv := item.get(meta_key):
                row[meta_key] = mv.strip()
        out.append(row)
    return out
```

### 3.4 默认回退计划

```python
_DEFAULT_STEPS = [
    {"id": "1", "title": "理解用户输入与上下文", "description": "澄清目标、约束与已知事实"},
    {"id": "2", "title": "执行并汇总", "description": "按计划逐步达成子目标并在最后整合结论"},
]
```

---

## 四、Planner System Prompt

**文件**: `backend/app/modules/prompts/planning.py`

```python
def build_planner_system_prompt() -> str:
    return """You are a planning assistant for ForgeAgent.

    ## Task
    Read the prior conversation and the user's current goal.
    Emit **only one JSON object** that lists abstract execution steps...

    ## Output rules
    - **Raw JSON only**: no markdown fences, no commentary
    - **Language**: use Simplified Chinese for `title` and `description`
    - **Shape**: {"steps":[{"id":"string","title":"Chinese title","description":"optional"}, ...]}

    ## Forbidden in any step object
    Do not include keys that imply tool invocation:
    `tool`, `args`, `tool_name`, `function`, `function_call`, `action`.
    """
```

---

## 五、重规划流程

### 5.1 触发来源

**文件**: `backend/app/modules/memory/learner_node.py`

Learner 节点合并两方意图：

```python
# 1. Actor 可设置 replan_requested=True（如工具调用失败）
actor_replan = bool(state.get("replan_requested"))

# 2. LLM 反思可返回 request_replan=true
llm_request_replan = ...

# 3. 合并意图
wants_replan = (not failed) and can_replan and (actor_replan or llm_request_replan)
```

### 5.2 条件边路由

**文件**: `backend/app/modules/execution/nodes.py`

```python
def route_after_learner(state: AgentState) -> Literal["planner", "done"]:
    if state.get("outcome") == "failed":
        return "done"
    if state.get("replan_requested"):
        return "planner"   # 回到 planner
    return "done"
```

### 5.3 Planner 侧重规划处理

```python
if state.get("replan_requested"):
    # 1. 递增计划版本号
    new_version = await task_repository.bump_plan_version(db, task_id)

    # 2. 写 replan 事件
    await event_repository.append_event(
        db, task_id, "planning", "replan",
        json.dumps({"plan_version": new_version}, ensure_ascii=False),
    )

    # 3. 增加 replan 计数
    out["replan_count"] = int(state.get("replan_count") or 0) + 1
    out["replan_requested"] = False
```

---

## 六、完整流程图

```
用户消息
    │
    ▼
┌─────────────────┐
│   planner_node  │ ←──────────┐
│  加载历史+黑板   │            │ (replan_requested=True)
│  调用规划 LLM   │            │
│  返回 plan_steps│            │
└────────┬────────┘            │
         │                    │
         ▼                    │
┌─────────────────┐            │
│   actor_node    │            │
│ (按步骤执行)    │            │
└────────┬────────┘            │
         │                    │
         ▼                    │
┌─────────────────┐            │
│  learner_node   │            │
│  反思+写黑板     │            │
│  设置 replan?   │────────────┘
└────────┬────────┘
         │
    route_after_learner
    ┌────┴────┐
    ↓         ↓
  done     planner
```

---

## 七、关键文件索引

| 文件 | 作用 |
|------|------|
| `modules/workflow/graph.py` | 工作流定义 |
| `modules/workflow/state.py` | AgentState 类型 |
| `modules/planning/nodes.py` | Planner 节点实现 |
| `modules/planning/llm.py` | LLM 调用与步骤规范化 |
| `modules/prompts/planning.py` | System Prompt |
| `modules/execution/nodes.py` | route_after_learner |
| `modules/memory/learner_node.py` | 重规划决策 |
| `repositories/task_repository.py` | bump_plan_version |
