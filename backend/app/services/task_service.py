"""任务用例服务：任务的创建、查询、补丁、删除与事件访问，并编排后台 Agent 执行。"""

import asyncio
import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppHTTPException
from app.shared.payload import payload_json_to_dict
from app.modules.planning.nodes import initial_force_replan_budget
from app.modules.workflow.graph import get_compiled_agent_graph
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
    """在单事务内完成「从指定用户消息重新执行」所需的记忆截断与任务分支清理。"""
    # 1. 校验消息归属与会话、且角色为用户
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
    # 2. 就地更新该用户消息正文
    await message_repository.update_message_content(db, row, content)
    # 3. 取消会话内活动任务并删除锚点起的任务（事件随任务级联删除）
    await task_repository.cancel_active_tasks_for_session(db, session_id)
    await task_repository.delete_tasks_for_branch_from_user_message(
        db,
        session_id=session_id,
        anchor_message_id=row.id,
        anchor_time=row.created_at,
    )
    # 4. 删除该消息之后的会话消息
    await message_repository.delete_messages_after(db, session_id, row.id)


async def create_task_start_mock(
    session_id: str,
    user_message: str,
    *,
    reuse_user_message_id: int | None = None,
) -> TaskCreateResponse:
    """创建运行中任务并异步启动 Agent 图；可选指定用户消息 id 作为复用锚点。"""
    # 1. 校验用户输入非空
    content = (user_message or "").strip()
    if not content:
        raise AppHTTPException(
            "用户消息不能为空",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    # 2. 生成任务 id 与 SSE 路径（响应体引用）
    task_id = str(uuid4())
    stream_path = f"/api/v1/tasks/{task_id}/events/stream"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            # 3. 校验会话存在；写入或复用用户消息以得到 source_user_message_id
            chat = await session_repository.get_session_by_id(db, session_id)
            if chat is None:
                raise AppHTTPException(
                    "会话不存在",
                    code="NOT_FOUND",
                    status_code=404,
                )
            if reuse_user_message_id is None:
                user_msg = await message_repository.add_message(
                    db,
                    session_id=session_id,
                    role="user",
                    content=content,
                )
                source_mid = user_msg.id
            else:
                await _apply_reuse_user_message(
                    db,
                    session_id=session_id,
                    reuse_user_message_id=reuse_user_message_id,
                    content=content,
                )
                source_mid = reuse_user_message_id
            # 4. 持久化任务行（running）
            task_row = Task(
                id=task_id,
                session_id=session_id,
                status="running",
                plan_version=1,
                source_user_message_id=source_mid,
            )
            await task_repository.add_task(db, task_row)
    # 5. 与请求 DB 会话脱钩后调度后台图（避免会话冲突）
    asyncio.create_task(run_agent_task(task_id, session_id, content))
    return TaskCreateResponse(task_id=task_id, events_stream_path=stream_path)


async def run_agent_task(
    task_id: str,
    session_id: str,
    user_message: str,
) -> None:
    """在独立协程中运行编译后的 Agent 图，并按终态回写任务与（成功时）助手消息。"""
    settings = get_settings()
    graph = get_compiled_agent_graph()
    # 1. 构造初始状态（任务与会话 id、用户输入、重规划预算等）
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
        # 2. 执行图（规划/执行节点内落库事件）
        result = await graph.ainvoke(initial)
        outcome = result.get("outcome")
        # 3. 若任务未被取消则按 outcome 收敛任务状态与摘要
        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await task_repository.get_task_by_id(db, task_id)
                if task is None:
                    return
                if task.status == "cancelled":
                    return
                if outcome == "success":
                    task.status = "success"
                    task.summary = result.get("summary") or "任务已完成"
                    task.error_message = None
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
    except Exception as exc:  # noqa: BLE001
        # 图执行未捕获异常：尽力将任务标为失败并追加 execution/error 事件
        logger.exception("agent graph failed for task %s", task_id)
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    task = await task_repository.get_task_by_id(db, task_id)
                    if task is None:
                        return
                    if task.status == "cancelled":
                        return
                    task.status = "failed"
                    task.error_message = str(exc)
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
    if status is not None and status not in _VALID_TASK_STATUS:
        raise AppHTTPException(
            f"无效的状态过滤: {status}",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    rows, total = await task_repository.list_tasks(
        db,
        limit=limit,
        offset=offset,
        status=status,
        session_id=session_id,
    )
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
        await db.flush()
    return await get_task_detail(db, task_id)


async def get_task_detail(db: AsyncSession, task_id: str) -> TaskDetail:
    """单任务详情：表字段 + 最近一次 plan_created 推导出的 plan。"""
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    plan_event = await event_repository.get_latest_plan_created(db, task_id)
    plan_dict = payload_json_to_dict(plan_event.payload_json if plan_event else None)
    plan = plan_dict if plan_dict and "steps" in plan_dict else None
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
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    if task.status in ("pending", "running"):
        raise AppHTTPException(
            "任务仍在执行或排队中，无法删除",
            code="CONFLICT",
            status_code=409,
        )
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
    """任务事件分页/增量列表，与 SSE 单条结构对齐。"""
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )
    rows = await event_repository.list_events(
        db, task_id, after_seq=after_seq, limit=limit
    )
    return TaskEventsResponse(
        events=[
            TaskEventItem(
                seq=e.seq,
                ts=e.ts,
                module=e.module,
                kind=e.kind,
                payload=payload_json_to_dict(e.payload_json),
            )
            for e in rows
        ]
    )
