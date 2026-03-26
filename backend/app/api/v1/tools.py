"""工具注册表只读 REST（内置 / MCP / Skill 元数据统一形状）。"""

from fastapi import APIRouter

from app.schemas.tools import ToolsListResponse
from app.services import tool_service

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=ToolsListResponse)
async def get_tools() -> ToolsListResponse:
    """返回当前进程内可见的工具列表（阶段2 为内置占位；阶段3 对齐真实注册表）。"""
    # 1. 委托 tool_service 组装 ToolsListResponse
    return tool_service.list_tools_public()
