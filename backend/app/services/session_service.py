"""会话用例服务（记忆：会话线程与消息列表）。"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppHTTPException
from app.models.session import Session as ChatSession
from app.repositories import message_repository, session_repository
from app.schemas.session import MessagesListResponse, MessageOut, SessionCreateResponse


async def create_session(db: AsyncSession, body_title: str | None) -> SessionCreateResponse:
    """新建一条会话记录并返回其业务 ID。"""
    # 1. 生成全局唯一 session_id（UUID）
    # 2. 写入 sessions 表
    # 3. 组装 SessionCreateResponse
    sid = str(uuid4())
    row = ChatSession(id=sid, title=body_title)
    await session_repository.create_session_row(db, row)
    return SessionCreateResponse(session_id=sid)


async def list_messages_for_session(
    db: AsyncSession,
    session_id: str,
    *,
    limit: int,
    offset: int,
) -> MessagesListResponse:
    """拉取某会话下的消息，时间顺序与 id 升序一致。"""
    # 1. 确认会话存在
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    # 2. 分页查询 messages
    rows = await message_repository.list_messages(
        db, session_id, limit=limit, offset=offset
    )
    # 3. 映射为 API 契约的 MessageOut 列表
    return MessagesListResponse(
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in rows
        ]
    )
