"""内置工具的 LangChain 定义：``@tool`` + Pydantic ``args_schema`` 作为参数与执行的单一来源。"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import BaseTool, tool
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.tools import ToolItem


# 输入参数 Pydantic 模型
class EchoInput(BaseModel):
    """echo 入参；兼容历史字段名 ``message``。"""

    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(
        ...,
        description="要回显的文本。",
        # AliasChoices 是 Pydantic v2 提供的工具，用于定义字段的多个别名
        validation_alias=AliasChoices("text", "message"),
    )


class MockSearchInput(BaseModel):
    """mock_search 入参。"""

    query: str = Field(
        default="",
        description="检索关键词；可省略表示空查询。",
    )


@tool("echo", args_schema=EchoInput)
async def echo_tool(text: str) -> dict[str, Any]:
    """回显输入文本（开发调试用内置工具）。"""
    return {"echoed": text}


@tool("mock_search", args_schema=MockSearchInput)
async def mock_search_tool(query: str = "") -> dict[str, Any]:
    """占位：返回固定检索结果，供列表与执行链路联调。"""
    q = query or ""
    return {
        "query": q,
        "results": [
            {
                "title": "mock 文档 A",
                "snippet": f"与「{q or '（空查询）'}」相关的占位摘要（内置 mock_search）。",
            },
            {
                "title": "mock 文档 B",
                "snippet": "ForgeAgent 执行链路联调用固定结果，可换真实检索后保持 schema。",
            },
        ],
    }


# 内置工具元组
BUILTIN_LC_TOOLS: tuple[BaseTool, ...] = (echo_tool, mock_search_tool)

# 工具字典
BUILTIN_LC_TOOLS_BY_NAME: dict[str, BaseTool] = {t.name: t for t in BUILTIN_LC_TOOLS}


def _parameters_json_schema(tool: BaseTool) -> dict[str, Any] | None:
    """自 LangChain 工具的 ``args_schema`` 生成 JSON Schema。"""
    schema_cls = getattr(tool, "args_schema", None)
    if schema_cls is None:
        return None
    if isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
        return schema_cls.model_json_schema()
    return None


def langchain_tool_to_tool_item(
    tool: BaseTool,
    *,
    source: Literal["builtin", "mcp", "skill"] = "builtin",
) -> ToolItem:
    """将已注册的 ``BaseTool`` 转为对外 ``ToolItem``（含 ``parameters`` schema）。"""
    desc = (tool.description or "").strip()
    return ToolItem(
        name=tool.name,
        description=desc if desc else tool.name,
        source=source,
        read_only=True,
        parameters=_parameters_json_schema(tool),
    )


def list_builtin_tools_from_lc() -> list[ToolItem]:
    """由 LangChain 内置工具列表生成 API 用 ``ToolItem``。"""
    return [langchain_tool_to_tool_item(t) for t in BUILTIN_LC_TOOLS]
