"""内置工具元数据（与 LangChain/LangGraph 绑定实现留在后续阶段）。"""

from app.schemas.tools import ToolItem


def list_builtin_tools() -> list[ToolItem]:
    """返回进程内始终可用的内置工具清单。"""
    # 1. 登记与 PRD「四模块」之工具能力对齐的占位实现名
    return [
        ToolItem(
            name="echo",
            description="回显输入文本（开发调试用内置工具）",
            source="builtin",
            read_only=True,
        ),
        ToolItem(
            name="mock_search",
            description="占位：返回固定检索结果，供列表与执行链路联调",
            source="builtin",
            read_only=True,
        ),
    ]
