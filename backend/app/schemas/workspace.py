"""GET /api/v1/workspace 响应体与条目模型（OpenAPI / 前端共用）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceEntry(BaseModel):
    """单层列举中的一行（文件或文件夹）。"""

    name: str
    path: str
    is_dir: bool = Field(..., description="是否为目录")
    size_bytes: int | None = Field(
        None,
        description="文件大小（字节）；目录为 null",
    )


class WorkspaceSnapshotResponse(BaseModel):
    """单次列举请求的完整响应（根路径、当前目录、上级、列表）。"""

    workspace_root: str = Field(..., description="工作区根绝对路径")
    current_path: str = Field(..., description="当前正在列举的目录绝对路径")
    parent_path: str | None = Field(
        None,
        description="上级目录绝对路径；已在根目录时为 null",
    )
    workspace_listing: list[WorkspaceEntry]
    workspace_listing_truncated: bool = Field(
        ...,
        description="条目数是否因上限被截断",
    )
