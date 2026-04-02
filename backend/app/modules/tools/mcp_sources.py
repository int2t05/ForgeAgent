"""从 settings.mcp 解析工具元数据：mock 内嵌、stdio/sse 经 MCP Client 拉取。"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.tools.mcp_client import McpToolMeta, mcp_client_manager, normalize_mcp_transport
from app.schemas.tools import ToolItem

logger = logging.getLogger(__name__)


def _tools_from_mock_server(raw: dict[str, Any], server_name: str) -> list[ToolItem]:
    tool_specs = raw.get("tools")
    if not isinstance(tool_specs, list):
        return []
    out: list[ToolItem] = []
    for idx, spec in enumerate(tool_specs):
        if not isinstance(spec, dict):
            continue
        tname = spec.get("name")
        if not tname:
            tname = f"{server_name}_tool_{idx}"
        tname = str(tname).strip()
        desc = str(spec.get("description") or f"MCP「{server_name}」提供的工具").strip()
        out.append(
            ToolItem(
                name=tname,
                description=desc,
                source="mcp",
                read_only=bool(spec.get("read_only", True)),
                mcp_server_name=server_name,
            )
        )
    return out


def _tools_from_mcp_meta(server_name: str, metas: list[McpToolMeta]) -> list[ToolItem]:
    return [
        ToolItem(
            name=m.name,
            description=m.description or f"MCP「{server_name}」提供的工具",
            source="mcp",
            read_only=None,
            parameters=m.input_schema,
            mcp_server_name=server_name,
        )
        for m in metas
    ]


def _is_mock_mcp_row(raw: dict[str, Any]) -> bool:
    t = normalize_mcp_transport(raw.get("transport"))
    if t in ("stdio", "sse"):
        return False
    if t == "mock":
        return True
    tools = raw.get("tools")
    return bool(
        isinstance(tools, list)
        and not raw.get("url")
        and not raw.get("command")
    )


def tools_from_mcp_settings_mock(mcp_servers: list[Any]) -> list[ToolItem]:
    out: list[ToolItem] = []
    for raw in mcp_servers:
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            continue
        if not _is_mock_mcp_row(raw):
            continue
        name = str(raw.get("name") or "mcp").strip() or "mcp"
        out.extend(_tools_from_mock_server(raw, name))
    return out


async def tools_from_mcp_settings(mcp_servers: list[Any]) -> list[ToolItem]:
    mock_items = tools_from_mcp_settings_mock(mcp_servers)

    real_cfgs = [
        cfg
        for cfg in mcp_servers
        if isinstance(cfg, dict)
        and cfg.get("enabled") is not False
        and normalize_mcp_transport(cfg.get("transport")) in ("stdio", "sse", "http")
    ]
    if not real_cfgs:
        return mock_items

    try:
        await mcp_client_manager.connect(real_cfgs)
    except Exception:
        logger.error("MCP 连接池刷新失败", exc_info=True)

    real_items: list[ToolItem] = []
    for server_name, metas in (await mcp_client_manager.list_all_tools()).items():
        real_items.extend(_tools_from_mcp_meta(server_name, metas))

    return real_items + mock_items
