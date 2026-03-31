"""LangGraph 运行时状态（规划 / 执行 / 重规划 共享）。"""

from typing import Literal, NotRequired, TypedDict


class AgentState(TypedDict, total=False):
    """单次任务在图内的可合并状态；入口由 task_service 注入必填字段。"""

    task_id: str
    session_id: str
    user_message: str
    replan_count: int
    max_replan_attempts: int
    force_replan_budget: int

    plan_steps: list[dict[str, str]]
    current_step_index: int

    replan_requested: bool
    outcome: NotRequired[Literal["success", "failed"]]
    summary: NotRequired[str | None]
    error_message: NotRequired[str | None]
