"""进程内工具注册表快照：启动与设置变更后刷新，GET /tools 只读该快照。"""

import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.tools import ToolItem, ToolsListResponse
from app.services.settings_service import get_settings_public
from app.tools.builtin import list_builtin_tools
from app.tools.mcp_sources import tools_from_mcp_settings
from app.tools.skill_sources import tools_from_skill_paths


class ToolRegistry:
    """
    统一注册表：内置 + MCP（当前为 mock 元数据）+ Skill。

    合并规则：同名工具以先声明者为准（内置优先，其次 MCP，最后 Skill）。
    """

    def __init__(self) -> None:
        """初始化空快照与异步锁。"""
        # 异步上下文锁，用于保护并发访问共享可变状态
        self._lock = asyncio.Lock()
        self._tools: list[ToolItem] = list_builtin_tools()

    def _merge(self, parts: Sequence[Sequence[ToolItem]]) -> list[ToolItem]:
        """按顺序合并的多段工具列表，后段同名条目被忽略。"""
        # 1. 维护已见名称集合，避免跨来源重复
        seen: set[str] = set()
        merged: list[ToolItem] = []
        for group in parts:
            for t in group:
                if t.name in seen:
                    continue
                seen.add(t.name)
                merged.append(t)
        # 2. 返回稳定顺序的列表
        return merged

    async def refresh(self, db: AsyncSession) -> None:
        """
        根据 settings_kv 重建快照（在 main lifespan 与 PUT /settings 后调用）。

        业务流程：
        1. 读取 MCP / skills_paths 非密钥配置
        2. 分别组装 builtin、mcp、skill 三层 ToolItem
        3. 按优先级合并后更新内存
        """
        async with self._lock:
            # 1. 拉取当前对外设置视图
            settings = await get_settings_public(db)
            builtins = list_builtin_tools()
            mcp_part = tools_from_mcp_settings(settings.mcp)
            skill_part = tools_from_skill_paths(settings.skills_paths)
            # 2. 合并为单一列表并写回
            self._tools = self._merge((builtins, mcp_part, skill_part))

    def list_tools_public(self) -> ToolsListResponse:
        """返回与 OpenAPI 一致的只读响应。"""
        # 1. 拷贝列表避免调用方改内部状态
        return ToolsListResponse(tools=list(self._tools))


tool_registry = ToolRegistry()  # 全局单例
