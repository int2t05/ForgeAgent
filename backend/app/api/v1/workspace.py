"""工作区只读 HTTP：单层目录列举与可选的配置热同步。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db
from app.modules.tools.registry import tool_registry
from app.schemas.workspace import WorkspaceEntry, WorkspaceSnapshotResponse
from app.shared.workspace_snapshot import WorkspacePathError, build_workspace_browser_state

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceSnapshotResponse)
async def get_workspace_snapshot(
    path: str | None = Query(
        None,
        description="要列举的目录绝对路径；省略则列举当前工作区根",
    ),
    reload_config: bool = Query(
        False,
        description="为 true 时从数据库重读工作区根并重建工具注册表（侧栏「刷新」）",
    ),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceSnapshotResponse:
    """返回单层文件列表；reload_config 与 PUT /settings 后工具刷新一致。"""
    # 1. 按需从 settings_kv 同步显式根并重建内置工具绑定
    if reload_config:
        await tool_registry.refresh(db)
    # 2. 列举目录（路径越界等转为 400）
    try:
        raw = build_workspace_browser_state(get_settings(), path)
    except WorkspacePathError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    listing = [WorkspaceEntry.model_validate(x) for x in raw["workspace_listing"]]
    return WorkspaceSnapshotResponse(
        workspace_root=raw["workspace_root"],
        current_path=raw["current_path"],
        parent_path=raw["parent_path"],
        workspace_listing=listing,
        workspace_listing_truncated=bool(raw["workspace_listing_truncated"]),
    )
