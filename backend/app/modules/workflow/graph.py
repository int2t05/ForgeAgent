"""LangGraph Agent 状态图：规划、执行、条件重规划回环至再规划。"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
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


_compiled: Any | None = None
_checkpointer: BaseCheckpointSaver | None = None


def init_compiled_agent_graph(checkpointer: BaseCheckpointSaver) -> None:
    """在进程启动（FastAPI lifespan）时注入持久化 checkpointer 并编译图。"""
    global _compiled, _checkpointer
    _checkpointer = checkpointer
    _compiled = build_agent_graph().compile(checkpointer=checkpointer)


def get_checkpoint_guard_ref() -> BaseCheckpointSaver | None:
    """供关闭生命周期使用；外部不应操作图状态。"""
    return _checkpointer


def reset_compiled_agent_graph_for_tests() -> None:
    """测试隔离：清空编译图与 checkpointer 引用（不关闭底层连接）。"""
    shutdown_compiled_agent_graph()


def shutdown_compiled_agent_graph() -> None:
    """释放图单例引用（须在 ``close_langgraph_checkpointer`` 之后调用，避免悬空调用）。"""
    global _compiled, _checkpointer
    _compiled = None
    _checkpointer = None


def get_compiled_agent_graph():
    """返回已在 lifespan 中初始化的编译图。"""
    if _compiled is None:
        raise RuntimeError(
            "Agent 图未初始化：请确认 FastAPI lifespan 已调用 init_compiled_agent_graph，"
            "或在测试中显式初始化。"
        )
    return _compiled
