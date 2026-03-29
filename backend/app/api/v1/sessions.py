"""会话 REST（记忆：创建线程与拉取消息列表）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.session import MessagesListResponse, SessionCreate, SessionCreateResponse
from app.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionCreateResponse)
async def post_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> SessionCreateResponse:
    """创建新会话（POST /api/v1/sessions）。"""
    # 1. 生成并持久化会话行
    # 2. 返回 session_id
    return await session_service.create_session(db, body.title)


@router.get("/{session_id}/messages", response_model=MessagesListResponse)
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> MessagesListResponse:
    """分页返回某会话下的用户/助手/系统消息。"""
    # 1. 校验会话存在，否则 404
    # 2. 按 id 正序分页查询 messages 并组装响应
    return await session_service.list_messages_for_session(
        db, session_id, limit=limit, offset=offset
    )
