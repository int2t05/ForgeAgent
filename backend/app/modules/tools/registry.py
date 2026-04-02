"""进程内工具注册表快照：启动与设置变更后刷新，GET /tools 只读该快照。"""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.workspace_config import set_explicit_workspace_root
from app.modules.tools.builtin_lc import list_builtin_tools_from_lc
from app.modules.tools.builtin_executor import execute_builtin
from app.modules.tools.mcp_client import mcp_client_manager
from app.modules.tools.mcp_sources import tools_from_mcp_settings
from app.schemas.tools import ToolItem, ToolsListResponse
from app.services.settings_service import get_settings_public


class ToolRegistry:
    """统一注册表：内置 + MCP（mock 与真实 transport）。

    合并规则：同名工具以先声明者为准（内置优先，其次 MCP）。
    Skill 目录仅用于 ``SKILL.md`` 上下文导入，不产生工具项。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        tools = list_builtin_tools_from_lc()
        self._tools: list[ToolItem] = tools
        self._by_name: dict[str, ToolItem] = {t.name: t for t in tools}

    async def refresh(self, db: AsyncSession) -> None:
        """按 settings_kv 与当前进程环境重建工具快照并同步工作区显式根。"""
        # 1. 丢弃 Settings 单例缓存，便于 .env 等变更在无重启进程时生效
        get_settings.cache_clear()
        async with self._lock:
            # 2. 读库并写入工作区覆盖路径（供 resolved_agent_workspace_path）
            settings = await get_settings_public(db)
            set_explicit_workspace_root(settings.agent_workspace_root)
            # 3. 重建内置工具（绑定新根）并与 MCP 元数据合并
            builtins = list_builtin_tools_from_lc()
            mcp_part = await tools_from_mcp_settings(settings.mcp)
            seen: set[str] = set()
            merged: list[ToolItem] = []
            for t in (*builtins, *mcp_part):
                if t.name in seen:
                    continue
                seen.add(t.name)
                merged.append(t)
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
        payload = dict(args) if args else {}
        if item.source == "builtin":
            return await execute_builtin(name, payload)
        if item.source == "mcp":
            return await self._execute_mcp(item, payload)
        return {
            "ok": False,
            "error": f"来源为 {item.source} 的工具尚未接入执行器",
        }

    async def _execute_mcp(
        self, item: ToolItem, args: dict[str, Any]
    ) -> dict[str, Any]:
        """通过 McpClientManager 调用真实 MCP 工具。"""
        server_name = item.mcp_server_name
        if not server_name:
            return {"ok": False, "error": f"MCP 工具缺少 server 名称: {item.name}"}
        if server_name not in mcp_client_manager.connected_server_names:
            return {"ok": False, "error": f"MCP Server 未连接: {server_name}"}
        return await mcp_client_manager.call_tool(server_name, item.name, args)


tool_registry = ToolRegistry()
