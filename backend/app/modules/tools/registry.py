"""进程内工具注册表快照：启动与设置变更后刷新，GET /tools 只读该快照。"""

import asyncio
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tools.builtin import list_builtin_tools
from app.modules.tools.builtin_executor import execute_builtin
from app.modules.tools.mcp_sources import tools_from_mcp_settings
from app.modules.tools.skill_sources import tools_from_skill_paths
from app.schemas.tools import ToolItem, ToolsListResponse
from app.services.settings_service import get_settings_public


class ToolRegistry:
    """
    统一注册表：内置 + MCP（当前为 mock 元数据）+ Skill。

    合并规则：同名工具以先声明者为准（内置优先，其次 MCP，最后 Skill）。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tools: list[ToolItem] = list_builtin_tools()

    def _merge(self, parts: Sequence[Sequence[ToolItem]]) -> list[ToolItem]:
        """按内置优先顺序合并多路工具列表，同名仅保留首次出现。"""
        seen: set[str] = set()
        merged: list[ToolItem] = []
        for group in parts:
            for t in group:
                if t.name in seen:
                    continue
                seen.add(t.name)
                merged.append(t)
        return merged

    async def refresh(self, db: AsyncSession) -> None:
        """根据 settings_kv 重建快照（在 main lifespan 与 PUT /settings 后调用）。"""
        async with self._lock:
            settings = await get_settings_public(db)
            builtins = list_builtin_tools()
            mcp_part = tools_from_mcp_settings(settings.mcp)
            skill_part = tools_from_skill_paths(settings.skills_paths)
            self._tools = self._merge((builtins, mcp_part, skill_part))

    def list_tools_public(self) -> ToolsListResponse:
        """返回当前快照中的工具列表封装为 API 响应模型。"""
        return ToolsListResponse(tools=list(self._tools))

    def _get_tool_item(self, name: str) -> ToolItem | None:
        """按名称在快照中查找工具元数据。"""
        for t in self._tools:
            if t.name == name:
                return t
        return None

    async def execute(
        self, name: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """按名称分派执行并返回统一结构化结果（供 tool_result 等事件序列化）。"""
        args = dict(args) if args else {}
        item = self._get_tool_item(name)
        if item is None:
            return {"ok": False, "error": f"未知工具: {name}"}
        if item.source == "builtin":
            return await execute_builtin(name, args)
        return {
            "ok": False,
            "error": f"来源为 {item.source} 的工具尚未接入执行器",
        }


tool_registry = ToolRegistry()
