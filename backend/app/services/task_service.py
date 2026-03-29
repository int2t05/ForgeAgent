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
from app.schemas.event import TaskEventItem, TaskEventsResponse
from app.schemas.task import (
    TaskCreateResponse,
    TaskDetail,
    TaskListResponse,
    TaskSummary,
)

logger = logging.getLogger(__name__)

_VALID_TASK_STATUS = frozenset(
    {"pending", "running", "success", "failed", "cancelled"}  # 不可变的集合
)


async def create_task_start_mock(
    session_id: str,
    user_message: str,
) -> TaskCreateResponse:
    """创建 running 任务并异步调度 LangGraph 执行器（不占用来请求的 DB 会话）。"""
    task_id = str(uuid4())
    stream_path = f"/api/v1/tasks/{task_id}/events/stream"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            # 1. 校验会话存在
            chat = await session_repository.get_session_by_id(db, session_id)
            if chat is None:
                raise AppHTTPException(
                    "会话不存在",
                    code="NOT_FOUND",
                    status_code=404,
                )
            # 2. 追加一条用户消息（记忆）
            await message_repository.add_message(
                db,
                session_id=session_id,
                role="user",
                content=user_message,
            )
            # 3. 创建任务行，状态 running
            task_row = Task(
                id=task_id,
                session_id=session_id,
                status="running",
                plan_version=1,
            )
            await task_repository.add_task(db, task_row)
    # 4. 事务已提交后启动后台协程，避免与 Depends(get_db) 生命周期竞态
    asyncio.create_task(run_agent_task(task_id, session_id, user_message))
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
    }  # 初始化状态
    try:
        result = await graph.ainvoke(initial)  # 异步调用
        outcome = result.get("outcome")
        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await task_repository.get_task_by_id(db, task_id)
                if task is None:
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
        db, limit=limit, offset=offset, status=status
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
