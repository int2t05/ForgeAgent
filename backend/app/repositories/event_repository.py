"""任务事件追加（执行可观测：保证同一 task_id 下 seq 单调且唯一）。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_event import TaskEvent


async def append_event(
    session: AsyncSession,
    task_id: str,
    module: str,
    kind: str,
    payload_json: str | None = None,
) -> TaskEvent:
    """1. 在同一会话/事务内查询当前最大 seq。2. 插入 seq+1。3. 依赖表级 UNIQUE(task_id,seq) 防止竞态重复。"""
    stmt = select(func.coalesce(func.max(TaskEvent.seq), 0)).where(
        TaskEvent.task_id == task_id
    )
    result = await session.execute(stmt)
    max_seq: int = result.scalar_one()
    next_seq = max_seq + 1
    event = TaskEvent(
        task_id=task_id,
        seq=next_seq,
        module=module,
        kind=kind,
        payload_json=payload_json,
    )
    session.add(event)
    await session.flush()
    await session.refresh(event)
    return event
