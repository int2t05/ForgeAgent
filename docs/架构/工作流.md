# 工作流详解

## LangGraph 状态机

```
START
  │
  ▼
┌─────────────────────────────────────────────────────┐
│                   LangGraph Agent                     │
│                                                      │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│   │ Planner  │───▶│  Actor   │───▶│  Learner  │     │
│   └──────────┘    └──────────┘    └──────────┘     │
│        ▲               │               │             │
│        │               │               ▼             │
│        │               │    route_after_learner      │
│        │               │        │         │          │
│        │               │      replan   done         │
│        │               │        │         │          │
│        └───────────────┴────────┘         │          │
│                                            ▼          │
│                                           END         │
└─────────────────────────────────────────────────────┘
```

## AgentState

```python
class AgentState(TypedDict, total=False):
    task_id: str
    session_id: str
    user_message: str
    plan_steps: list[dict]        # 计划步骤
    current_step_index: int
    blackboard_notes: list[str]   # 黑板反思
    actor_tool_trace: list[dict]  # 工具轨迹
    replan_requested: bool
    outcome: str                  # success/failed
    summary: str | None
```

## 节点职责

| 节点 | 输入 | 输出 |
|------|------|------|
| **Planner** | user_message, blackboard | plan_steps |
| **Actor** | plan_steps, user_message | summary, tool_trace |
| **Learner** | tool_trace, outcome | blackboard_notes, replan |

## ReAct 循环

```
while True:
    LLM 生成 thought + action/final_answer
    │
    ├── action?
    │   └── 执行工具 → Observation → 继续循环
    │
    └── final_answer?
        └── 退出循环
```
