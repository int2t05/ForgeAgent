"""任务表 tasks 数据访问。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task

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
    # 1. 加载任务行并递增版本（重规划可观测与详情展示）
    row = await get_task_by_id(session, task_id)
    if row is None:
        msg = f"任务不存在: {task_id}"
        raise ValueError(msg)
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
) -> tuple[list[Task], int]:
    """可选 status 过滤；按 created_at 倒序分页；返回 (行列表, 总条数)。"""
    # 1. 构造 count 与 data 查询（带或不带 status）
    if status is not None:
        count_stmt = select(func.count()).select_from(Task).where(Task.status == status)
        stmt = (
            select(Task)
            .where(Task.status == status)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    else:
        count_stmt = select(func.count()).select_from(Task)  # 生成 COUNT(*) SQL 函数
        stmt = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)

    # 2. 执行 count
    total_result = await session.execute(count_stmt)
    total = int(total_result.scalar_one())
    # 3. 执行分页列表
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


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


