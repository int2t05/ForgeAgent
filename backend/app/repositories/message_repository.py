"""会话消息表 messages 数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


async def add_message(
    session: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
) -> Message:
    """在指定会话下插入一条消息并返回持久化后的 ORM 对象。"""
    row = Message(session_id=session_id, role=role, content=content)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def list_messages(
    session: AsyncSession,
    session_id: str,
    *,
    limit: int,
    offset: int,
) -> list[Message]:
    """按消息 id 升序分页返回某会话的消息（对话时间序）。"""
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.id.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
