"""进程内工具注册表快照：启动与设置变更后刷新，GET /tools 只读该快照。"""

import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tools.builtin import list_builtin_tools
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
        return ToolsListResponse(tools=list(self._tools))


tool_registry = ToolRegistry()
