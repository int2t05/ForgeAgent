"""从设置中的 MCP 描述拉取工具元数据；支持文档化 mock transport（无外部 Server 时验收与单测）。"""

from typing import Any

from app.schemas.tools import ToolItem

_TRANSPORT_MOCK = "mock"


def tools_from_mcp_settings(mcp_servers: list[Any]) -> list[ToolItem]:
    """
    将 settings.mcp 列表转换为 ToolItem（source=mcp）。

    支持：
    - transport=mock（或省略 url 且存在 tools 数组时视为 mock）：从同条配置内嵌的 tools 读取名称与描述。
    - enabled=false：跳过该 Server。
    """
    out: list[ToolItem] = []
    for raw in mcp_servers:
        if not isinstance(raw, dict):
            continue
        if raw.get("enabled") is False:
            continue
        name = str(raw.get("name") or "mcp").strip() or "mcp"
        transport = str(raw.get("transport") or "").lower()
        tool_specs = raw.get("tools")
        is_mock = transport == _TRANSPORT_MOCK or (
            isinstance(tool_specs, list) and not raw.get("url")
        )
        if not is_mock or not isinstance(tool_specs, list):
            continue
        for idx, spec in enumerate(tool_specs):
            if not isinstance(spec, dict):
                continue
            tname = spec.get("name")
            if not tname:
                tname = f"{name}_tool_{idx}"
            tname = str(tname).strip()
            desc = str(spec.get("description") or f"MCP「{name}」提供的工具").strip()
            out.append(
                ToolItem(
                    name=tname,
                    description=desc,
                    source="mcp",
                    read_only=bool(spec.get("read_only", True)),
                )
            )
    return out
