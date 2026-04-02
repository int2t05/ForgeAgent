"""LangGraph Agent 编排：Planner → Actor → Learner 线性边，Learner 出口再条件回到 Planner 或结束。

Planner 只产出抽象步骤；Actor 在步内 ReAct 并汇总答复；Learner 写黑板并可在预算内触发再规划。
编译图与 checkpointer 在应用 lifespan 内单例初始化，供任务执行复用。
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.modules.execution.nodes import actor_node, route_after_learner
from app.modules.memory.learner_node import learner_node
from app.modules.planning.nodes import planner_node
from app.modules.workflow.state import AgentState


def build_agent_graph() -> StateGraph:
    """返回已挂接三节点与 Learner 条件边的 ``StateGraph`` 构造器（未 ``compile``）。"""
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("actor", actor_node)
    builder.add_node("learner", learner_node)
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
