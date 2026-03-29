"""LangGraph 最小图：Planner → Executor →（条件）Replan → Planner。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    executor_node,
    planner_node,
    replan_record_node,
    route_after_executor,
)
from app.agent.state import AgentState


def build_agent_graph() -> StateGraph:
    """构建未 compile 的 StateGraph（便于单测注入 mock）。"""
    # 1. 添加节点
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("replan_record", replan_record_node)
    # 2. 添加边
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_conditional_edges(
        "executor",
        route_after_executor,
        {"replan": "replan_record", "done": END},
    )
    builder.add_edge("replan_record", "planner")
    return builder


_compiled = None


def get_compiled_agent_graph():
    """进程内单例编译图，避免重复构建。"""
    global _compiled  # 在函数内部声明全局变量
    if _compiled is None:
        _compiled = build_agent_graph().compile()
    return _compiled
