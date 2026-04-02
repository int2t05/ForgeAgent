"""LangGraph ``AgentState``：各节点通过合并返回值更新同一 TypedDict。

黑板条目跨回合保留在会话侧；Planner 再次运行时可消费 Learner 写入的摘要。
"""

from typing import Any, Literal, NotRequired, TypedDict


class AgentState(TypedDict, total=False):
    """单次任务运行时各节点可读写字段的类型并集（入口注入 + 节点回写）。"""

    task_id: str
    session_id: str
    user_message: str

    replan_count: int
    max_replan_attempts: int

    plan_steps: list[dict[str, Any]]
    current_step_index: int

    blackboard_notes: NotRequired[list[str]]
    actor_tool_trace: NotRequired[list[dict[str, Any]]]

    replan_requested: bool
    outcome: NotRequired[Literal["success", "failed"]]
    summary: NotRequired[str | None]
    error_message: NotRequired[str | None]
