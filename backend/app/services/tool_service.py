"""工具注册表只读服务（HTTP 层委托进程内 ToolRegistry 快照）。"""

from app.schemas.tools import ToolsListResponse
from app.tools.registry import tool_registry


def list_tools_public() -> ToolsListResponse:
    """返回当前 API 可用的工具元数据列表（与注册表快照一致）。"""
    # 1. 读取最近一次 refresh 合并后的工具（builtin / mcp / skill）
    return tool_registry.list_tools_public()
