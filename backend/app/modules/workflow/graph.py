"""工作流编排：LangGraph Agent 状态图编译前定义。

入口经 framework_router 分流为 plan_execute（planner→executor→可选重规划）
或 react（react_executor 直达结束）；executor 与 replan_record 构成重规划回环。
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.modules.execution.nodes import executor_node, route_after_executor
from app.modules.execution.react_agent import react_executor_node
from app.modules.planning.framework_router import (
    framework_router_node,
    route_after_framework,
)
from app.modules.planning.nodes import planner_node, replan_record_node
from app.modules.workflow.state import AgentState


def build_agent_graph() -> StateGraph:
    """组装 LangGraph 状态图（仅定义节点与边，未 compile）。"""
    # 1. 注册节点：认知路由、规划、计划执行、ReAct、重规划记录
    builder = StateGraph(AgentState)
    builder.add_node("framework_router", framework_router_node)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("react_executor", react_executor_node)
    builder.add_node("replan_record", replan_record_node)
    # 2. START → 框架路由；按认知模式进入 planner 或 react_executor
    builder.add_edge(START, "framework_router")
    builder.add_conditional_edges(
        "framework_router",
        route_after_framework,
        {"planner": "planner", "react": "react_executor"},
    )
    builder.add_edge("planner", "executor")
    builder.add_edge("react_executor", END)
    # 3. 执行结束或进入重规划；重规划后回到 planner
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
