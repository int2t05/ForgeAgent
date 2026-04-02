"""会话用例服务（记忆：会话线程与消息列表）。"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppHTTPException
from app.models.message import Message
from app.modules.memory.checkpointer import delete_checkpoint_threads
from app.models.session import Session as ChatSession
from app.repositories import message_repository, session_repository, task_repository
from app.schemas.common import OperationOkResponse
from app.modules.memory.llm_context_budget import estimate_messages_tokens
from app.modules.memory.session_blackboard import decode_blackboard_json
from app.modules.memory.session_context import session_messages_to_chat_messages
from app.schemas.session import (
    MessageCreate,
    MessageOut,
    MessageUpdate,
    MessagesListResponse,
    SessionContextResponse,
    SessionContextSummaryMeta,
    SessionContextTokenBudget,
    SessionContextWindowItem,
    SessionCreateResponse,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
    SessionUpdate,
)
from app.shared.langchain_content import message_content_text

_PREVIEW_MAX_CHARS = 480
_MESSAGE_ROLES = frozenset({"user", "assistant", "system"})


def _truncate_preview(text: str, max_chars: int = _PREVIEW_MAX_CHARS) -> str:
    """将正文截断为会话列表预览长度，超出部分以省略号收尾。"""
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


async def _require_session(db: AsyncSession, session_id: str) -> ChatSession:
    """若会话存在则返回 ORM 行，否则抛出业务 404。"""
    chat = await session_repository.get_session_by_id(db, session_id)
    if chat is None:
        raise AppHTTPException(
            "会话不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    return chat


async def _require_message_in_session(
    db: AsyncSession,
    session_id: str,
    message_id: int,
) -> Message:
    """若消息存在且属于该会话则返回 ORM 行，否则抛出业务 404。"""
    row = await message_repository.get_message_by_id(db, message_id)
    if row is None or row.session_id != session_id:
        raise AppHTTPException(
            "消息不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    return row


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
    ids = [r.id for r in rows]
    last_by_sid = await message_repository.map_last_message_content_by_session_ids(
        db, ids
    )
    return SessionListResponse(
        items=[
            SessionSummary(
                id=r.id,
                title=r.title,
                created_at=r.created_at,
                last_message_preview=(
                    _truncate_preview(last_by_sid[r.id])
                    if r.id in last_by_sid and last_by_sid[r.id].strip()
                    else None
                ),
            )
            for r in rows
        ],
        total=total,
    )


async def get_session_detail(db: AsyncSession, session_id: str) -> SessionDetail:
    """返回单条会话元数据。"""
    chat = await _require_session(db, session_id)
    return SessionDetail(id=chat.id, title=chat.title, created_at=chat.created_at)


async def get_session_context_preview(
    db: AsyncSession, session_id: str
) -> SessionContextResponse:
    """返回会话黑板 + 进入规划侧的消息窗口及 token 粗估（不调用摘要 LLM）。"""
    chat = await _require_session(db, session_id)
    settings = get_settings()
    max_n = max(1, int(settings.session_memory_max_messages))

    total = await message_repository.count_messages_for_session(db, session_id)
    rows = await message_repository.list_recent_messages(db, session_id, limit=max_n)
    lc_msgs = session_messages_to_chat_messages(rows)
    window: list[SessionContextWindowItem] = []
    for row, lm in zip(rows, lc_msgs, strict=True):
        mtype = getattr(lm, "type", None)
        if not isinstance(mtype, str) or not mtype:
            mtype = "human"
        window.append(
            SessionContextWindowItem(
                id=row.id,
                role=row.role,
                created_at=row.created_at,
                llm_type=mtype,
                llm_content=message_content_text(lm.content),
            )
        )

    est = estimate_messages_tokens(None, lc_msgs)
    board = decode_blackboard_json(chat.blackboard_notes_json)
    thr = int(settings.session_summarize_when_over)
    summary_eligible = bool(settings.session_conversation_summary_enabled) and len(
        lc_msgs
    ) > thr

    return SessionContextResponse(
        session_id=session_id,
        blackboard_notes=board,
        window=window,
        session_message_total=total,
        window_max_messages=max_n,
        summary=SessionContextSummaryMeta(
            enabled=bool(settings.session_conversation_summary_enabled),
            summarize_when_over=thr,
            keep_recent=int(settings.session_summary_keep_recent),
            eligible=summary_eligible,
        ),
        tokens=SessionContextTokenBudget(
            estimated_input=est,
            llm_max_input_tokens=settings.llm_max_input_tokens,
            llm_context_window_tokens=int(settings.llm_context_window_tokens),
            llm_reserved_completion_tokens=int(settings.llm_reserved_completion_tokens),
        ),
    )


async def update_session(
    db: AsyncSession, session_id: str, body: SessionUpdate
) -> SessionDetail:
    """更新会话标题等可写字段。"""
    chat = await _require_session(db, session_id)
    if "title" in body.model_fields_set:
        await session_repository.update_session_title(db, chat, body.title)
    return SessionDetail(id=chat.id, title=chat.title, created_at=chat.created_at)


async def create_session(db: AsyncSession, body_title: str | None) -> SessionCreateResponse:
    """新建会话并返回业务 ID。"""
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
    """拉取某会话下的消息，按 id 升序。"""
    await _require_session(db, session_id)
    rows = await message_repository.list_messages(
        db, session_id, limit=limit, offset=offset
    )
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
    await _require_session(db, session_id)
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
    await _require_session(db, session_id)
    row = await _require_message_in_session(db, session_id, message_id)
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
    await _require_session(db, session_id)
    row = await _require_message_in_session(db, session_id, message_id)
    await message_repository.delete_message_row(db, row)
    return OperationOkResponse()


async def delete_session(db: AsyncSession, session_id: str) -> OperationOkResponse:
    """删除会话及其消息、子任务与事件；进行中任务存在时拒绝。"""
    await _require_session(db, session_id)
    if await task_repository.session_has_active_tasks(db, session_id):
        raise AppHTTPException(
            "会话下仍有进行中的任务，请待任务结束或先删除这些任务后再删除会话",
            code="CONFLICT",
            status_code=409,
        )
    # LangGraph thread_id == task_id：先清独立 checkpoint 库表行，再清业务库
    task_ids = await task_repository.list_task_ids_for_session(db, session_id)
    await delete_checkpoint_threads(get_settings(), task_ids)
    await session_repository.delete_session_by_id(db, session_id)
    return OperationOkResponse()
