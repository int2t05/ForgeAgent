"""会话用例服务（记忆：会话线程与消息列表）。"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppHTTPException
from app.models.session import Session as ChatSession
from app.repositories import message_repository, session_repository, task_repository

_MESSAGE_ROLES = frozenset({"user", "assistant", "system"})
from app.schemas.common import OperationOkResponse
from app.schemas.session import (
    MessageCreate,
    MessageOut,
    MessageUpdate,
    MessagesListResponse,
    SessionCreateResponse,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
    SessionUpdate,
)


async def list_sessions_page(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> SessionListResponse:
    """分页列出会话概要，按创建时间倒序。"""
    rows, total = await session_repository.list_sessions_page(
        db, limit=limit, offset=offset
    )
    return SessionListResponse(
        items=[
            SessionSummary(id=r.id, title=r.title, created_at=r.created_at)
            for r in rows
        ],
        total=total,
    )


async def get_session_detail(db: AsyncSession, session_id: str) -> SessionDetail:
    """返回单条会话元数据。"""
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    return SessionDetail(id=chat.id, title=chat.title, created_at=chat.created_at)


async def update_session(
    db: AsyncSession, session_id: str, body: SessionUpdate
) -> SessionDetail:
    """更新会话标题等可写字段。"""
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    if "title" in body.model_fields_set:
        await session_repository.update_session_title(db, chat, body.title)
    return SessionDetail(id=chat.id, title=chat.title, created_at=chat.created_at)


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


async def append_message(
    db: AsyncSession, session_id: str, body: MessageCreate
) -> MessageOut:
    """在会话下追加一条消息（不触发 Agent）。"""
    if body.role not in _MESSAGE_ROLES:
        raise AppHTTPException(
            "无效的 role，须为 user / assistant / system",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    row = await message_repository.add_message(
        db,
        session_id=session_id,
        role=body.role,
        content=body.content,
    )
    return MessageOut(
        id=row.id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )


async def update_message(
    db: AsyncSession,
    session_id: str,
    message_id: int,
    body: MessageUpdate,
) -> MessageOut:
    """更新指定会话内一条消息的正文。"""
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    row = await message_repository.get_message_by_id(db, message_id)
    if row is None or row.session_id != session_id:
        raise AppHTTPException(
            "消息不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    await message_repository.update_message_content(db, row, body.content)
    return MessageOut(
        id=row.id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )


async def delete_message(
    db: AsyncSession,
    session_id: str,
    message_id: int,
) -> OperationOkResponse:
    """删除会话内一条消息。"""
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    row = await message_repository.get_message_by_id(db, message_id)
    if row is None or row.session_id != session_id:
        raise AppHTTPException(
            "消息不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    await message_repository.delete_message_row(db, row)
    return OperationOkResponse()


async def delete_session(db: AsyncSession, session_id: str) -> OperationOkResponse:
    """删除会话及其消息、子任务与事件（库级级联）；进行中任务存在时拒绝。"""
    # 1. 确认会话存在
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    # 2. 若有未终态任务则冲突，避免与后台 Agent 写入竞态
    if await task_repository.session_has_active_tasks(db, session_id):
        raise AppHTTPException(
            "会话下仍有进行中的任务，请待任务结束或先删除这些任务后再删除会话",
            code="CONFLICT",
            status_code=409,
        )
    # 3. 删除会话行
    await session_repository.delete_session_by_id(db, session_id)
    return OperationOkResponse()
