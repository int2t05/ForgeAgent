"""任务事件表 task_events 数据访问（seq 单调语义）。"""

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_event import TaskEvent


async def append_event(
    session: AsyncSession,
    task_id: str,
    module: str,
    kind: str,
    payload_json: str | None = None,
) -> TaskEvent:
    """在同一 DB 事务内为某任务追加下一条事件行（单条 INSERT + RETURNING，避免先 SELECT MAX）。"""
    next_seq = (
        select(func.coalesce(func.max(TaskEvent.seq), 0) + 1)
        .where(TaskEvent.task_id == task_id)
        .scalar_subquery()
    )
    stmt = (
        insert(TaskEvent)
        .values(
            task_id=task_id,
            seq=next_seq,
            module=module,
            kind=kind,
            payload_json=payload_json,
        )
        .returning(TaskEvent)
    )
    result = await session.scalars(stmt)
    return result.one()


async def list_events(
    session: AsyncSession,
    task_id: str,
    *,
    after_seq: int | None,
    limit: int,
) -> list[TaskEvent]:
    """按 seq 升序取事件；after_seq 表示严格大于该序号。"""
    stmt = select(TaskEvent).where(TaskEvent.task_id == task_id)
    if after_seq is not None:
        stmt = stmt.where(TaskEvent.seq > after_seq)
    stmt = stmt.order_by(TaskEvent.seq.asc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_latest_plan_created(
    session: AsyncSession, task_id: str
) -> TaskEvent | None:
    """取该任务最新一条 kind=plan_created 的事件（用于详情页 plan）。"""
    stmt = (
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id, TaskEvent.kind == "plan_created")
        .order_by(TaskEvent.seq.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
