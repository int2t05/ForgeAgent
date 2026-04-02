"""工具注册表只读 REST 模型。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolItem(BaseModel):
    """统一工具描述：名称、说明、来源、可选只读标记与可选 JSON Schema 参数。"""

    name: str
    description: str
    source: Literal["builtin", "mcp"]
    read_only: bool | None = None
    parameters: dict[str, Any] | None = Field(
        default=None,
        description="OpenAPI/JSON Schema 风格的入参定义（与 LangChain args_schema 对齐时可提供）。",
    )
    mcp_server_name: str | None = Field(
        default=None,
        description="MCP 来源工具所属 Server 名称；source='mcp' 时由注册表填充。",
    )


class ToolsListResponse(BaseModel):
    """GET /tools 响应。"""

    tools: list[ToolItem] = Field(default_factory=list)
