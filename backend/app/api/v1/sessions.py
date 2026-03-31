"""会话 REST（记忆：会话 CRUD 与消息 CRUD）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.common import OperationOkResponse
from app.schemas.session import (
    MessageCreate,
    MessageOut,
    MessageUpdate,
    MessagesListResponse,
    SessionCreate,
    SessionCreateResponse,
    SessionDetail,
    SessionListResponse,
    SessionUpdate,
)
from app.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def get_sessions(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SessionListResponse:
    """分页列出会话。"""
    return await session_service.list_sessions_page(db, limit=limit, offset=offset)


@router.post("", response_model=SessionCreateResponse)
async def post_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> SessionCreateResponse:
    """创建新会话（POST /api/v1/sessions）。"""
    return await session_service.create_session(db, body.title)


@router.get("/{session_id}/messages", response_model=MessagesListResponse)
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> MessagesListResponse:
    """分页返回某会话下的用户/助手/系统消息。"""
    return await session_service.list_messages_for_session(
        db, session_id, limit=limit, offset=offset
    )


@router.post("/{session_id}/messages", response_model=MessageOut)
async def post_session_message(
    session_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """在会话下追加一条消息（不启动 Agent）。"""
    return await session_service.append_message(db, session_id, body)


@router.patch("/{session_id}/messages/{message_id}", response_model=MessageOut)
async def patch_session_message(
    session_id: str,
    message_id: int,
    body: MessageUpdate,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """更新会话内一条消息正文。"""
    return await session_service.update_message(db, session_id, message_id, body)


@router.delete("/{session_id}/messages/{message_id}", response_model=OperationOkResponse)
async def delete_session_message(
    session_id: str,
    message_id: int,
    db: AsyncSession = Depends(get_db),
) -> OperationOkResponse:
    """删除会话内一条消息。"""
    return await session_service.delete_message(db, session_id, message_id)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """读取会话元数据。"""
    return await session_service.get_session_detail(db, session_id)


@router.patch("/{session_id}", response_model=SessionDetail)
async def patch_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """更新会话元数据（如标题）。"""
    return await session_service.update_session(db, session_id, body)


@router.delete("/{session_id}", response_model=OperationOkResponse)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> OperationOkResponse:
    """删除会话及其关联数据；存在进行中任务时返回 409。"""
    return await session_service.delete_session(db, session_id)
