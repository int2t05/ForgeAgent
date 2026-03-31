"""内置工具元数据（与 ``builtin_lc`` 中 LangChain 定义对齐）。"""

from app.modules.tools.builtin_lc import list_builtin_tools_from_lc
from app.schemas.tools import ToolItem


def list_builtin_tools() -> list[ToolItem]:
    """返回进程内始终可用的内置工具清单（含 JSON Schema 参数）。"""
    return list_builtin_tools_from_lc()
