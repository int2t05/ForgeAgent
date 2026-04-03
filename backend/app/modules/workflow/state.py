"""LangGraph ``AgentState``：Plan-Act-Learn 三角循环状态定义。

Plan: 获取会话上下文 → 生成步骤
Act: 每步循环执行 → 收集工具上下文
Learn: 总结归纳 → 反思 → 判断重规划 or 生成最终回答
"""

from typing import Any, Literal, NotRequired, TypedDict


class AgentState(TypedDict, total=False):
    """Plan-Act-Learn 三角循环状态。"""

    task_id: str
    session_id: str
    user_message: str

    replan_count: int
    max_replan_attempts: int

    plan_steps: list[dict[str, Any]]
    current_step_index: int

    blackboard_notes: NotRequired[list[str]]

    act_context: NotRequired[dict[str, Any]]
    act_tool_trace: NotRequired[list[dict[str, Any]]]
    act_step_results: NotRequired[list[dict[str, Any]]]

    learn_reflection: NotRequired[str]
    learn_should_replan: NotRequired[bool]
    learn_final_answer: NotRequired[str]

    replan_requested: bool
    outcome: NotRequired[Literal["success", "failed"]]
    summary: NotRequired[str | None]
    error_message: NotRequired[str | None]
