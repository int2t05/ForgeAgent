"""会话消息表 messages 数据访问。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


async def get_message_by_id(session: AsyncSession, message_id: int) -> Message | None:
    """按主键取一条消息。"""
    stmt = select(Message).where(Message.id == message_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


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


async def update_message_content(
    session: AsyncSession, row: Message, content: str
) -> Message:
    """更新消息正文并刷新。"""
    row.content = content
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def delete_message_row(session: AsyncSession, row: Message) -> None:
    """删除一条消息行。"""
    await session.delete(row)
    await session.flush()


async def delete_messages_after(
    session: AsyncSession, session_id: str, after_message_id: int
) -> None:
    """删除某会话内 id 大于 after_message_id 的全部消息（用于从该用户消息起重做对话）。"""
    stmt = delete(Message).where(
        Message.session_id == session_id,
        Message.id > after_message_id,
    )
    await session.execute(stmt)
    await session.flush()
