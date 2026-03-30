"""任务相关请求/响应模型。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    """POST /tasks 请求体：挂载会话并携带用户自然语言输入。"""

    session_id: str
    user_message: str


class TaskCreateResponse(BaseModel):
    """POST /tasks 响应：任务 id 与事件流相对路径。"""

    task_id: str
    events_stream_path: str


class TaskSummary(BaseModel):
    """列表页单行任务摘要。"""

    id: str
    session_id: str
    status: str
    summary: str | None
    plan_version: int
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """GET /tasks 分页响应。"""

    items: list[TaskSummary] = Field(default_factory=list)
    total: int


class TaskDetail(BaseModel):
    """GET /tasks/{id} 详情：含可选 plan（来自事件或日后表字段）。"""

    id: str
    session_id: str
    status: str
    summary: str | None
    plan_version: int
    plan: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None


class TaskPatch(BaseModel):
    """PATCH /tasks/{id}：当前仅支持取消未结束任务。"""

    status: Literal["cancelled"]
