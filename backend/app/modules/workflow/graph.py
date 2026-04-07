"""LangGraph Agent 编排：Plan → Act → Learn 三角循环。

Plan: 获取会话上下文 → 生成步骤
Act: 每步循环执行 → 收集工具上下文
Learn: 总结归纳 → 反思 → 判断重规划 or 生成最终回答

图结构：
START → plan → act → learn → (条件边)
                                    ├─ plan (重规划)
                                    └─ END (完成)
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, TypeAlias

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.modules.workflow.state import AgentState

AgentNode: TypeAlias = Callable[[AgentState], Awaitable[dict[str, Any]]]
LearnRoute: TypeAlias = Callable[[AgentState], Literal["plan", "done"]]


def _default_workflow_nodes() -> tuple[AgentNode, AgentNode, AgentNode, LearnRoute]:
    """惰性加载默认节点，避免循环依赖。"""
    from app.modules.execution.nodes import act_node
    from app.modules.memory.learn import learn_node, route_after_learn
    from app.modules.planning.nodes import plan_node

    return plan_node, act_node, learn_node, route_after_learn


def build_agent_graph(
    *,
    plan: AgentNode | None = None,
    act: AgentNode | None = None,
    learn: AgentNode | None = None,
    route_after_learn: LearnRoute | None = None,
) -> StateGraph:
    """构建 Plan-Act-Learn 三角循环图。

    节点命名：
    - plan: 规划节点
    - act: 执行节点
    - learn: 学习节点

    边：
    - START → plan
    - plan → act
    - act → learn
    - learn → (条件边) → plan 或 END
    """
    if (
        plan is None
        or act is None
        or learn is None
        or route_after_learn is None
    ):
        dp, da, dl, dr = _default_workflow_nodes()
        plan = plan or dp
        act = act or da
        learn = learn or dl
        route_after_learn = route_after_learn or dr

    builder = StateGraph(AgentState)
    builder.add_node("plan", plan)
    builder.add_node("act", act)
    builder.add_node("learn", learn)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "act")
    builder.add_edge("act", "learn")
    builder.add_conditional_edges(
        "learn",
        route_after_learn,
        {"plan": "plan", "done": END},
    )

    return builder


_compiled: Any | None = None
_checkpointer: BaseCheckpointSaver | None = None


def init_compiled_agent_graph(checkpointer: BaseCheckpointSaver) -> None:
    """初始化编译图单例。"""
    global _compiled, _checkpointer
    _checkpointer = checkpointer
    _compiled = build_agent_graph().compile(checkpointer=checkpointer)


def get_checkpoint_guard_ref() -> BaseCheckpointSaver | None:
    """返回当前 checkpointer 引用。"""
    return _checkpointer


def reset_compiled_agent_graph_for_tests() -> None:
    """测试用：重置编译图。"""
    shutdown_compiled_agent_graph()


def shutdown_compiled_agent_graph() -> None:
    """释放编译图与 checkpointer 引用。"""
    global _compiled, _checkpointer
    _compiled = None
    _checkpointer = None


def get_compiled_agent_graph():
    """返回已编译图单例。"""
    if _compiled is None:
        raise RuntimeError(
            "Agent 图未初始化：请确认 FastAPI lifespan 已调用 init_compiled_agent_graph。"
        )
    return _compiled
