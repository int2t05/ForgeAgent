"""工作流编排包：LangGraph 状态与编译图。

避免在 ``__init__`` 中导入 ``graph``，否则会与 ``planning.nodes`` / ``execution.nodes``
导入 ``workflow.state`` 时形成循环。

请直接从子模块引用：

    from app.modules.workflow.graph import build_agent_graph, get_compiled_agent_graph
    from app.modules.workflow.state import AgentState
"""
