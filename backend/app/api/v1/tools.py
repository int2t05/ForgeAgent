"""工具注册表只读 REST（内置 / MCP / Skill 元数据统一形状）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.modules.tools.registry import tool_registry
from app.schemas.tools import ToolsListResponse

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=ToolsListResponse)
async def get_tools() -> ToolsListResponse:
    """返回当前内存中的工具注册表快照（轻量；不在此接口上重建以免拖死事件循环）。"""
    return tool_registry.list_tools_public()


@router.post("/refresh", response_model=ToolsListResponse)
async def post_refresh_tools_registry(
    db: AsyncSession = Depends(get_db),
) -> ToolsListResponse:
    """重读环境变量与 settings_kv 并重建快照（改 TAVILY_API_KEY 或 MCP / Skills 后由前端主动调用）。"""
    await tool_registry.refresh(db)
    return tool_registry.list_tools_public()
