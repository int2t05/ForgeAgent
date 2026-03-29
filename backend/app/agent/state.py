"""LangGraph 运行时状态（规划 / 执行 / 重规划 共享）。"""

from typing import Literal, NotRequired, TypedDict


class AgentState(TypedDict, total=False):
    """单次任务在图内的可合并状态；入口由 task_service 注入必填字段。"""

    # --- 入口注入（必填） ---
    task_id: str
    session_id: str
    user_message: str
    replan_count: int
    max_replan_attempts: int
    #: 用户消息触发的「测试用」重规划剩余次数（每消耗一次走一轮 replan_record）
    force_replan_budget: int

    # --- 规划输出 ---
    plan_steps: list[dict[str, str]]
    current_step_index: int

    # --- 执行过程 ---
    replan_requested: bool
    outcome: NotRequired[Literal["success", "failed"]]
    summary: NotRequired[str | None]
    error_message: NotRequired[str | None]
