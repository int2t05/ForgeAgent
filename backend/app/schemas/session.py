"""会话与消息相关请求/响应模型（对齐 docs/api/API.md）。"""

from pydantic import BaseModel, Field

from app.schemas.json_datetime import JsonUtcDatetime


class SessionCreate(BaseModel):
    """POST /sessions 请求体。"""

    title: str | None = None


class SessionCreateResponse(BaseModel):
    """POST /sessions 响应。"""

    session_id: str


class SessionSummary(BaseModel):
    """GET /sessions 列表单项。"""

    id: str
    title: str | None
    created_at: JsonUtcDatetime
    last_message_preview: str | None = Field(
        default=None,
        description="最后一条消息正文摘要（列表接口填充；无消息时为 null）。",
    )


class SessionListResponse(BaseModel):
    """GET /sessions 分页响应。"""

    items: list[SessionSummary] = Field(default_factory=list)
    total: int


class SessionDetail(BaseModel):
    """GET /sessions/{id} 与 PATCH 后的会话元数据。"""

    id: str
    title: str | None
    created_at: JsonUtcDatetime


class SessionUpdate(BaseModel):
    """PATCH /sessions/{id} 请求体。"""

    title: str | None = None


class MessageCreate(BaseModel):
    """POST /sessions/{id}/messages 请求体。"""

    role: str
    content: str


class MessageUpdate(BaseModel):
    """PATCH .../messages/{id} 请求体。"""

    content: str


class MessageOut(BaseModel):
    """单条会话消息的对外表示。"""

    id: int
    role: str
    content: str
    created_at: JsonUtcDatetime


class MessagesListResponse(BaseModel):
    """GET /sessions/{id}/messages 响应。"""

    messages: list[MessageOut] = Field(default_factory=list)
