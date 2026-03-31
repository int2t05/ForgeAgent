"""LangGraph：Planner → Executor →（条件）Replan → Planner。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.modules.execution.nodes import executor_node, route_after_executor
from app.modules.planning.nodes import planner_node, replan_record_node
from app.modules.workflow.state import AgentState


def build_agent_graph() -> StateGraph:
    """构建未 compile 的 StateGraph（便于单测注入 mock）。"""
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("replan_record", replan_record_node)
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
    global _compiled
    if _compiled is None:
        _compiled = build_agent_graph().compile()
    return _compiled
