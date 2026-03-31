"""任务表 tasks 数据访问。"""

from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task

# 与「删除会话」「取消并重建任务」等互斥的进行中状态
_ACTIVE_DELETE_BLOCK_STATUSES = ("pending", "running")


async def add_task(session: AsyncSession, row: Task) -> Task:
    """插入任务行并刷新主键侧字段（此处主键为客户端 UUID）。"""
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_task_by_id(session: AsyncSession, task_id: str) -> Task | None:
    """按任务 id 查询单行。"""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def bump_plan_version(session: AsyncSession, task_id: str) -> int:
    """在同一事务内将任务的 plan_version 加一并返回新版本号。"""
    # 1. 加载任务行
    row = await get_task_by_id(session, task_id)
    if row is None:
        msg = f"任务不存在: {task_id}"
        raise ValueError(msg)
    # 2. 递增版本并刷盘，供重规划可观测与详情展示
    row.plan_version = int(row.plan_version) + 1
    session.add(row)
    await session.flush()
    return int(row.plan_version)


async def list_tasks(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: str | None,
    session_id: str | None = None,
) -> tuple[list[Task], int]:
    """可选 status / session_id 过滤；按 created_at 倒序分页；返回 (行列表, 总条数)。"""
    filters = []
    if status is not None:
        filters.append(Task.status == status)
    if session_id is not None:
        filters.append(Task.session_id == session_id)

    count_stmt = select(func.count()).select_from(Task)
    stmt = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    for f in filters:
        count_stmt = count_stmt.where(f)
        stmt = stmt.where(f)

    total_result = await session.execute(count_stmt)
    total = int(total_result.scalar_one())
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def cancel_active_tasks_for_session(
    session: AsyncSession, session_id: str
) -> None:
    """将该会话下 pending/running 任务标为 cancelled（用于用户从某条消息重新执行）。"""
    stmt = select(Task).where(
        Task.session_id == session_id,
        Task.status.in_(_ACTIVE_DELETE_BLOCK_STATUSES),
    )
    result = await session.execute(stmt)
    for row in result.scalars().all():
        row.status = "cancelled"
        if not row.error_message:
            row.error_message = "用户已取消"
        session.add(row)
    await session.flush()


async def delete_tasks_for_branch_from_user_message(
    session: AsyncSession,
    *,
    session_id: str,
    anchor_message_id: int,
    anchor_time: datetime,
) -> None:
    """删除某条用户消息锚点起的对话分支所关联的任务行（事件随 FK 级联删除）。"""
    # 1. 主条件：任务的 source_user_message_id 不早于锚点消息 id
    # 2. 兼容：source 为空时以任务 created_at 不早于锚点消息创建时间为准
    stmt = delete(Task).where(
        Task.session_id == session_id,
        or_(
            Task.source_user_message_id >= anchor_message_id,
            and_(
                Task.source_user_message_id.is_(None),
                Task.created_at >= anchor_time,
            ),
        ),
    )
    await session.execute(stmt)
    await session.flush()


async def session_has_active_tasks(session: AsyncSession, session_id: str) -> bool:
    """会话下是否存在尚未终态的任务（pending/running），用于删除会话前的冲突检测。"""
    stmt = (
        select(Task.id)
        .where(
            Task.session_id == session_id,
            Task.status.in_(_ACTIVE_DELETE_BLOCK_STATUSES),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def list_task_ids_for_session(session: AsyncSession, session_id: str) -> list[str]:
    """返回某会话下全部任务主键（与 LangGraph ``thread_id`` 对齐），用于清理 checkpoint。"""
    stmt = select(Task.id).where(Task.session_id == session_id)
    result = await session.execute(stmt)
    return [str(x) for x in result.scalars().all()]


