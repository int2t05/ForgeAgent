"""任务相关请求/响应模型。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.json_datetime import JsonUtcDatetime # type: ignore


class TaskCreate(BaseModel):
    """POST /tasks 请求体：挂载会话并携带用户自然语言输入。"""

    session_id: str
    user_message: str
    reuse_user_message_id: int | None = Field(
        default=None,
        description=(
            "复用已有用户消息并重新执行：更新该条正文、删除其后的消息、取消本会话未结束任务，"
            "并删除该条消息对应时刻及之后产生的任务与事件（级联），且不追加新的用户消息行"
        ),
    )


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
    created_at: JsonUtcDatetime
    updated_at: JsonUtcDatetime


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
    created_at: JsonUtcDatetime
    updated_at: JsonUtcDatetime
    error_message: str | None = None
    #: 仅 PATCH 取消且回滚了「本轮新建」用户消息时返回，供前端恢复输入框
    restored_user_message: str | None = None


class TaskPatch(BaseModel):
    """PATCH /tasks/{id}：当前仅支持取消未结束任务。"""

    status: Literal["cancelled"]
