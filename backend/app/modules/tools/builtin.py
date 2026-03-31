"""内置工具元数据（执行逻辑见 ``builtin_executor.execute_builtin``）。"""

from app.schemas.tools import ToolItem


def list_builtin_tools() -> list[ToolItem]:
    """返回进程内始终可用的内置工具清单。"""
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
