"""会话表 sessions 数据访问。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session as ChatSession


async def get_session_by_id(
    session: AsyncSession, session_id: str
) -> ChatSession | None:
    """按主键查询一条业务会话，不存在则 None。"""
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_session_row(session: AsyncSession, row: ChatSession) -> ChatSession:
    """插入新会话行并 flush/refresh 以得到数据库生成字段。"""
    session.add(row)  # 将新实体标记为"待写入"
    await session.flush()  # 立即将变更刷新到数据库
    await session.refresh(row)  # 从 DB 重新读取 row，确保自动生成字段最新
    return row


async def delete_session_by_id(session: AsyncSession, session_id: str) -> bool:
    """按 id 删除会话；依赖外键级联清理消息与子任务及其事件。不存在返回 False。"""
    row = await get_session_by_id(session, session_id)
    if row is None:
        return False
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
