"""工具注册表只读服务（阶段3 与 MCP/Skills 真实注册表对齐）。"""

from app.schemas.tools import ToolItem, ToolsListResponse


def list_tools_public() -> ToolsListResponse:
    """返回当前 API 可用的工具元数据列表（阶段2 内置占位）。"""
    # 1. 组装内置 ToolItem（名称、描述、source、权限提示）
    tools: list[ToolItem] = [
        ToolItem(
            name="echo",
            description="回显输入文本（开发调试用内置工具）",
            source="builtin",
            read_only=True,
        ),
        ToolItem(
            name="mock_search",
            description="占位：返回固定检索结果，阶段3 可替换为真实工具",
            source="builtin",
            read_only=True,
        ),
    ]
    # 2. 封装列表响应
    return ToolsListResponse(tools=tools)
