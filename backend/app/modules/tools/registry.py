"""进程内工具注册表快照：启动与设置变更后刷新，GET /tools 只读该快照。"""

import asyncio
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
        tools = list_builtin_tools()
        self._tools: list[ToolItem] = tools
        self._by_name: dict[str, ToolItem] = {t.name: t for t in tools}

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
        """根据 settings_kv 与当前环境变量重建快照（在 lifespan、GET /tools、PUT /settings 后调用）。"""
        # 使 .env / 进程环境变更（如 TAVILY_API_KEY）在不重载进程时可被 pydantic-settings 重新读取
        get_settings.cache_clear()
        async with self._lock:
            settings = await get_settings_public(db)
            builtins = list_builtin_tools()
            mcp_part = tools_from_mcp_settings(settings.mcp)
            skill_part = tools_from_skill_paths(settings.skills_paths)
            merged = self._merge((builtins, mcp_part, skill_part))
            self._tools = merged
            self._by_name = {t.name: t for t in merged}

    def list_tools_public(self) -> ToolsListResponse:
        """返回当前快照中的工具列表封装为 API 响应模型。"""
        return ToolsListResponse(tools=list(self._tools))

    def _get_tool_item(self, name: str) -> ToolItem | None:
        """按名称在快照中查找工具元数据。"""
        return self._by_name.get(name)

    async def execute(
        self, name: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """按名称分派执行并返回统一结构化结果（供 tool_result 等事件序列化）。"""
        item = self._by_name.get(name)
        if item is None:
            return {"ok": False, "error": f"未知工具: {name}"}
        if item.source != "builtin":
            return {
                "ok": False,
                "error": f"来源为 {item.source} 的工具尚未接入执行器",
            }
        return await execute_builtin(name, dict(args) if args else {})


tool_registry = ToolRegistry()
