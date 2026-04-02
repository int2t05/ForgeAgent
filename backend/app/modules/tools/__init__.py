"""工具域：内置、MCP（mock + 真实 transport）、Skills 元数据与统一注册表。"""

from app.modules.tools.mcp_client import mcp_client_manager
from app.modules.tools.registry import tool_registry

__all__ = ["mcp_client_manager", "tool_registry"]
