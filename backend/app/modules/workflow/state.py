"""LangGraph 运行时状态（规划 / 执行 / 重规划 共享）。"""

from typing import Any, Literal, NotRequired, TypedDict


class AgentState(TypedDict, total=False):
    """描述单次任务在 Agent 图内的可合并状态（入口注入与节点回写字段的并集）。"""

    task_id: str
    session_id: str
    user_message: str
    cognitive_mode: NotRequired[Literal["plan_execute", "react"]]
    framework_rationale: NotRequired[str]

    replan_count: int
    max_replan_attempts: int
    force_replan_budget: int

    plan_steps: list[dict[str, Any]]
    current_step_index: int

    replan_requested: bool
    outcome: NotRequired[Literal["success", "failed"]]
    summary: NotRequired[str | None]
    error_message: NotRequired[str | None]
