"""会话表 sessions 数据访问。"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.session import Session as ChatSession
from app.models.task import Task
from app.models.task_event import TaskEvent


async def get_session_by_id(
    session: AsyncSession, session_id: str
) -> ChatSession | None:
    """按主键查询一条业务会话，不存在则 None。"""
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_session_row(session: AsyncSession, row: ChatSession) -> ChatSession:
    """插入新会话行并 flush/refresh 以得到数据库生成字段。"""
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def delete_session_by_id(session: AsyncSession, session_id: str) -> bool:
    """按 id 删除会话：显式删除事件、任务、消息再删会话行，保证业务库无残留。"""
    row = await get_session_by_id(session, session_id)
    if row is None:
        return False
    tasks_in_session = select(Task.id).where(Task.session_id == session_id)
    await session.execute(
        delete(TaskEvent).where(TaskEvent.task_id.in_(tasks_in_session))
    )
    await session.execute(delete(Task).where(Task.session_id == session_id))
    await session.execute(delete(Message).where(Message.session_id == session_id))
    await session.delete(row)
    await session.flush()
    return True


async def list_sessions_page(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[ChatSession], int]:
    """按创建时间倒序分页返回会话；附带总数。"""
    count_stmt = select(func.count()).select_from(ChatSession)
    total_result = await session.execute(count_stmt)
    total = int(total_result.scalar_one())
    stmt = (
        select(ChatSession)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def update_session_title(
    session: AsyncSession,
    row: ChatSession,
    title: str | None,
) -> ChatSession:
    """更新会话标题。"""
    row.title = title
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row
