"""会话表 sessions 数据访问。"""

from sqlalchemy import select
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
