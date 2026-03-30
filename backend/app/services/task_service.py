"""任务用例服务（执行：创建、查询、事件；阶段4 LangGraph 最小闭环）。"""

import asyncio
import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_compiled_agent_graph
from app.agent.nodes import initial_force_replan_budget
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.exceptions import AppHTTPException
from app.models.task import Task
from app.repositories import (
    event_repository,
    message_repository,
    session_repository,
    task_repository,
)
from app.schemas.common import OperationOkResponse
from app.schemas.event import TaskEventItem, TaskEventsResponse
from app.schemas.task import (
    TaskCreateResponse,
    TaskDetail,
    TaskListResponse,
    TaskPatch,
    TaskSummary,
)

logger = logging.getLogger(__name__)

_VALID_TASK_STATUS = frozenset(
    {"pending", "running", "success", "failed", "cancelled"}
)


async def _apply_reuse_user_message(
    db: AsyncSession,
    *,
    session_id: str,
    reuse_user_message_id: int,
    content: str,
) -> None:
    """在已有事务内：校验并更新指定用户消息，取消会话内活跃任务，删除该消息之后的记忆。"""
    row = await message_repository.get_message_by_id(db, reuse_user_message_id)
    if row is None or row.session_id != session_id:
        raise AppHTTPException(
            "消息不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    if row.role != "user":
        raise AppHTTPException(
            "仅可基于用户消息重新执行",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    await message_repository.update_message_content(db, row, content)
    await task_repository.cancel_active_tasks_for_session(db, session_id)
    await message_repository.delete_messages_after(db, session_id, row.id)


async def create_task_start_mock(
    session_id: str,
    user_message: str,
    *,
    reuse_user_message_id: int | None = None,
) -> TaskCreateResponse:
    """创建 running 任务并异步调度 LangGraph。

    使用独立 ``AsyncSessionLocal`` 事务写入数据库，提交后再 ``asyncio.create_task`` 执行图，
    避免与请求内 ``Depends(get_db)`` 会话生命周期重叠。

    - 默认：追加一条 role=user 消息，再建任务。
    - ``reuse_user_message_id``：更新该条用户消息、截断后续 messages、取消本会话未结束任务，不追加新用户行。
    """
    content = (user_message or "").strip()
    if not content:
        raise AppHTTPException(
            "用户消息不能为空",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    task_id = str(uuid4())
    stream_path = f"/api/v1/tasks/{task_id}/events/stream"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            chat = await session_repository.get_session_by_id(db, session_id)
            if chat is None:
                raise AppHTTPException(
                    "会话不存在",
                    code="NOT_FOUND",
                    status_code=404,
                )
            if reuse_user_message_id is None:
                await message_repository.add_message(
                    db,
                    session_id=session_id,
                    role="user",
                    content=content,
                )
            else:
                await _apply_reuse_user_message(
                    db,
                    session_id=session_id,
                    reuse_user_message_id=reuse_user_message_id,
                    content=content,
                )
            task_row = Task(
                id=task_id,
                session_id=session_id,
                status="running",
                plan_version=1,
            )
            await task_repository.add_task(db, task_row)
    asyncio.create_task(run_agent_task(task_id, session_id, content))
    return TaskCreateResponse(
        task_id=task_id, events_stream_path=stream_path
    )  # 立即返回


async def run_agent_task(
    task_id: str,
    session_id: str,
    user_message: str,
) -> None:
    """阶段4：LangGraph Planner→Executor→条件重规划，写事件并收敛任务终态。"""
    settings = get_settings()
    graph = get_compiled_agent_graph()
    initial = {
        "task_id": task_id,
        "session_id": session_id,
        "user_message": user_message,
        "replan_count": 0,
        "max_replan_attempts": settings.max_replan_attempts,
        "replan_requested": False,
        "force_replan_budget": initial_force_replan_budget(user_message),
    }
    try:
        result = await graph.ainvoke(initial)  # 异步调用
        outcome = result.get("outcome")
        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await task_repository.get_task_by_id(db, task_id)
                if task is None:
                    return
                if task.status == "cancelled":
                    return
                # 1. 按图返回值写回终态与摘要/错误
                if outcome == "success":
                    task.status = "success"
                    task.summary = result.get("summary") or "任务已完成"
                    task.error_message = None
                    # 将助手回复写入会话消息（对话记忆，与 API.md messages 一致）
                    await message_repository.add_message(
                        db,
                        session_id=session_id,
                        role="assistant",
                        content=task.summary or "",
                    )
                elif outcome == "failed":
                    task.status = "failed"
                    task.error_message = result.get("error_message") or "任务失败"
                else:
                    task.status = "failed"
                    task.error_message = "Agent 未返回明确终态"
                db.add(task)
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent graph failed for task %s", task_id)
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    task = await task_repository.get_task_by_id(db, task_id)
                    if task is None:
                        return
                    if task.status == "cancelled":
                        return
                    # 1. 标记任务失败并记录错误信息
                    task.status = "failed"
                    task.error_message = str(exc)
                    db.add(task)
                    # 2. 追加 error 事件便于前端排障
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "error",
                        json.dumps({"message": str(exc)}, ensure_ascii=False),
                    )
        except Exception as inner:  # noqa: BLE001
            logger.exception(
                "could not persist failure for task %s: %s", task_id, inner
            )


async def list_tasks_page(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: str | None,
    session_id: str | None = None,
) -> TaskListResponse:
    """分页任务列表，含符合过滤条件的 total。"""
    # 1. 若带 status 则校验合法
    if status is not None and status not in _VALID_TASK_STATUS:
        raise AppHTTPException(
            f"无效的状态过滤: {status}",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    # 2. 仓储层查询 items + total
    rows, total = await task_repository.list_tasks(
        db,
        limit=limit,
        offset=offset,
        status=status,
        session_id=session_id,
    )
    # 3. 组装 TaskSummary 列表
    return TaskListResponse(
        items=[
            TaskSummary(
                id=r.id,
                session_id=r.session_id,
                status=r.status,
                summary=r.summary,
                plan_version=r.plan_version,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ],
        total=total,
    )


def _payload_to_dict(raw: str | None) -> dict | None:
    """将 task_events.payload_json 安全反序列化为 dict；非法则返回 None。"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def patch_task(
    db: AsyncSession,
    task_id: str,
    body: TaskPatch,
) -> TaskDetail:
    """部分更新任务；当前仅支持将 pending/running 标为 cancelled。"""
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    if body.status == "cancelled":
        if task.status not in ("pending", "running"):
            raise AppHTTPException(
                "仅可对未结束任务执行取消",
                code="CONFLICT",
                status_code=409,
            )
        task.status = "cancelled"
        if not task.error_message:
            task.error_message = "用户已取消"
        db.add(task)
        await db.flush()
    return await get_task_detail(db, task_id)


async def get_task_detail(db: AsyncSession, task_id: str) -> TaskDetail:
    """单任务详情：表字段 + 最近一次 plan_created 推导出的 plan。"""
    # 1. 读取任务行
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    # 2. 取最新 plan_created 的 payload 作为可展示 plan
    plan_event = await event_repository.get_latest_plan_created(db, task_id)
    plan_dict = _payload_to_dict(plan_event.payload_json if plan_event else None)
    plan = plan_dict if plan_dict and "steps" in plan_dict else None
    # 3. 填充 TaskDetail
    return TaskDetail(
        id=task.id,
        session_id=task.session_id,
        status=task.status,
        summary=task.summary,
        plan_version=task.plan_version,
        plan=plan,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error_message=task.error_message,
    )


async def delete_task(db: AsyncSession, task_id: str) -> OperationOkResponse:
    """删除单条任务及其事件；执行中或排队中的任务不可删。"""
    # 1. 加载任务
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    # 2. 未终态则与后台执行冲突
    if task.status in ("pending", "running"):
        raise AppHTTPException(
            "任务仍在执行或排队中，无法删除",
            code="CONFLICT",
            status_code=409,
        )
    # 3. 删除任务行（事件随 ORM cascade 清除）
    await db.delete(task)
    await db.flush()
    return OperationOkResponse()


async def list_task_events(
    db: AsyncSession,
    task_id: str,
    *,
    after_seq: int | None,
    limit: int,
) -> TaskEventsResponse:
    """任务事件分页/增量列表，供 REST 与日后 SSE 对齐结构。"""
    # 1. 确认任务存在（与空事件列表区分）
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    # 2. 按 seq 条件与上限查询
    rows = await event_repository.list_events(
        db, task_id, after_seq=after_seq, limit=limit
    )
    # 3. 映射为 TaskEventItem（payload 解析为 dict）
    return TaskEventsResponse(
        events=[
            TaskEventItem(
                seq=e.seq,
                ts=e.ts,
                module=e.module,
                kind=e.kind,
                payload=_payload_to_dict(e.payload_json),
            )
            for e in rows
        ]
    )
