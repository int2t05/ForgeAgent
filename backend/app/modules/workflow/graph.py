"""LangGraph Agent 编排：Planner → Actor → Learner，Learner 条件回到 Planner 或结束。

图结构与本模块耦合；具体节点实现通过 ``build_agent_graph`` 注入（默认惰性加载），
便于独立优化 / 单测替换 Planner、Actor、Learner 而无需改边定义。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, TypeAlias

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.modules.workflow.state import AgentState

AgentNode: TypeAlias = Callable[[AgentState], Awaitable[dict[str, Any]]]
LearnerRoute: TypeAlias = Callable[
    [AgentState], Literal["planner", "done"]
]


def _default_workflow_nodes() -> tuple[AgentNode, AgentNode, AgentNode, LearnerRoute]:
    """惰性加载默认可运行节点，避免 ``graph`` 与规划/执行模块的导入期循环依赖。"""
    from app.modules.execution.nodes import actor_node, route_after_learner
    from app.modules.memory.learner_node import learner_node
    from app.modules.planning.nodes import planner_node

    return planner_node, actor_node, learner_node, route_after_learner


def build_agent_graph(
    *,
    planner: AgentNode | None = None,
    actor: AgentNode | None = None,
    learner: AgentNode | None = None,
    route_after_learner: LearnerRoute | None = None,
) -> StateGraph:
    """返回已挂接节点与条件边的 ``StateGraph`` 构造器（未 ``compile``）。

    未传入的槽位使用默认 ``planner_node`` / ``actor_node`` / ``learner_node`` /
    ``route_after_learner``，在调用本函数时再导入对应模块。
    """
    if (
        planner is None
        or actor is None
        or learner is None
        or route_after_learner is None
    ):
        dp, da, dl, dr = _default_workflow_nodes()
        planner = planner or dp
        actor = actor or da
        learner = learner or dl
        route_after_learner = route_after_learner or dr

    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("actor", actor)
    builder.add_node("learner", learner)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "actor")
    builder.add_edge("actor", "learner")
    builder.add_conditional_edges(
        "learner",
        route_after_learner,
        {"planner": "planner", "done": END},
    )
    return builder


_compiled: Any | None = None
_checkpointer: BaseCheckpointSaver | None = None


def init_compiled_agent_graph(checkpointer: BaseCheckpointSaver) -> None:
    """注入 checkpointer 并完成编译图单例初始化（通常在 FastAPI lifespan 调用）。"""
    global _compiled, _checkpointer
    _checkpointer = checkpointer
    _compiled = build_agent_graph().compile(checkpointer=checkpointer)


def get_checkpoint_guard_ref() -> BaseCheckpointSaver | None:
    """返回当前全局 checkpointer 引用，供应用关闭链路与测试清理。"""
    return _checkpointer


def reset_compiled_agent_graph_for_tests() -> None:
    """测试用：丢弃编译图与 checkpointer 引用（不主动关闭底层连接）。"""
    shutdown_compiled_agent_graph()


def shutdown_compiled_agent_graph() -> None:
    """释放编译图与 checkpointer 全局引用（宜在 checkpointer 关闭之后调用）。"""
    global _compiled, _checkpointer
    _compiled = None
    _checkpointer = None


def get_compiled_agent_graph():
    """返回已编译图单例；未初始化时抛 ``RuntimeError``。"""
    if _compiled is None:
        raise RuntimeError(
            "Agent 图未初始化：请确认 FastAPI lifespan 已调用 init_compiled_agent_graph，"
            "或在测试中显式初始化。"
        )
    return _compiled
