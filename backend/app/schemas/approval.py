"""工具审批 REST 模型（请求/响应）。"""

from typing import Any

from pydantic import BaseModel, Field


class ApprovalItem(BaseModel):
    """单条审批请求的 API 表示。"""

    id: str
    task_id: str
    tool_name: str
    tool_args: dict[str, Any]
    status: str = Field(description="pending / approved / rejected / timeout / cancelled")


class ApprovalListResponse(BaseModel):
    """GET 待审批列表响应。"""

    items: list[ApprovalItem] = Field(default_factory=list)


class ApproveBody(BaseModel):
    """批准/拒绝请求体（预留扩展字段，当前可空）。"""

    pass


class ApproveResponse(BaseModel):
    """批准/拒绝操作响应。"""

    ok: bool = True
    message: str = ""
