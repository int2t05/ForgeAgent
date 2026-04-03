"""工具审批 REST 端点：人工批准/拒绝/查询待审批请求。"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.exceptions import AppHTTPException
from app.modules.execution.approval import (
    ApprovalStatus,
    approval_manager,
)
from app.schemas.approval import (
    ApprovalItem,
    ApprovalListResponse,
    ApproveBody,
    ApproveResponse,
)

router = APIRouter(prefix="/tasks/{task_id}/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalListResponse)
async def list_pending_approvals(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApprovalListResponse:
    """列出指定任务下当前 pending 的审批请求。"""
    items = approval_manager.get_pending(task_id)
    return ApprovalListResponse(
        items=[
            ApprovalItem(
                id=r.id,
                task_id=r.task_id,
                tool_name=r.tool_name,
                tool_args=r.tool_args,
                status=r.status.value,
            )
            for r in items
        ]
    )


@router.post("/{approval_id}/approve", response_model=ApproveResponse)
async def approve_tool(
    task_id: str,
    approval_id: str,
    body: ApproveBody | None = None,
) -> ApproveResponse:
    """批准一条待审批的敏感工具执行请求。"""
    ok = approval_manager.approve(approval_id)
    if not ok:
        raise AppHTTPException(
            "审批请求不存在、已处理或已超时",
            code="APPROVAL_NOT_PENDING",
            status_code=409,
        )
    return ApproveResponse(ok=True, message="已批准执行")


@router.post("/{approval_id}/reject", response_model=ApproveResponse)
async def reject_tool(
    task_id: str,
    approval_id: str,
    body: ApproveBody | None = None,
) -> ApproveResponse:
    """拒绝一条待审批的敏感工具执行请求。"""
    ok = approval_manager.reject(approval_id)
    if not ok:
        raise AppHTTPException(
            "审批请求不存在、已处理或已超时",
            code="APPROVAL_NOT_PENDING",
            status_code=409,
        )
    return ApproveResponse(ok=True, message="已拒绝执行")
