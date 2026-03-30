"""任务 REST（执行：列表/创建/详情/事件；SSE 流阶段5）。"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.exceptions import AppHTTPException
from app.repositories import task_repository
from app.schemas.event import TaskEventsResponse
from app.schemas.common import OperationOkResponse
from app.schemas.task import (
    TaskCreate,
    TaskCreateResponse,
    TaskDetail,
    TaskListResponse,
    TaskPatch,
)
from app.services import event_stream_service, task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
async def get_tasks(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(
        None, description="pending|running|success|failed|cancelled"
    ),
    session_id: str | None = Query(
        None, description="仅返回该会话下的任务（仍按 created_at 倒序）"
    ),
) -> TaskListResponse:
    """仪表盘：分页列出任务，可按状态 / 会话筛选。"""
    return await task_service.list_tasks_page(
        db, limit=limit, offset=offset, status=status, session_id=session_id
    )


@router.post("", response_model=TaskCreateResponse)
async def post_task(body: TaskCreate) -> TaskCreateResponse:
    """创建任务并异步执行；可选 ``reuse_user_message_id`` 时由 service 层截断记忆并取消活跃任务。"""
    return await task_service.create_task_start_mock(
        body.session_id,
        body.user_message,
        reuse_user_message_id=body.reuse_user_message_id,
    )


@router.get("/{task_id}/events/stream")
async def get_task_events_stream(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    after_seq: int | None = Query(
        None,
        ge=0,
        description="仅推送 seq > after_seq 的事件；与 GET /events 语义一致",
    ),
    last_event_id: int | None = Query(
        None,
        ge=0,
        description="与 after_seq 二选一；兼容文档中的断线重连续传",
    ),
) -> StreamingResponse:
    """订阅任务事件：text/event-stream，data 与 GET /events 单条结构一致。"""
    # 1. 校验任务存在（否则 404）。
    task = await task_repository.get_task_by_id(db, task_id)
    if task is None:
        raise AppHTTPException(
            "任务不存在",
            code="NOT_FOUND",
            status_code=404,
        )

    # 续传优先级：after_seq > last_event_id > Last-Event-ID 头
    start_after = after_seq if after_seq is not None else last_event_id
    # 2. 解析 Last-Event-ID（若 query 未传 after_seq）以支持 EventSource 重连。
    if start_after is None:
        # Last-Event-ID 是 SSE 规范定义的标准请求头，浏览器在断线重连时会自动带上此头
        raw_leid = request.headers.get("Last-Event-ID")
        if raw_leid is not None:
            try:
                start_after = int(raw_leid)
            except ValueError:
                start_after = None
    if start_after is None:
        start_after = 0

    generator = event_stream_service.iter_task_event_sse(
        task_id,
        after_seq=start_after,
    )
    # 3. 返回流式响应（轮询已提交行 + 终态后短时结束）。
    return StreamingResponse(
        generator,
        media_type="text/event-stream",  # SSE 标准 Content-Type
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}/events", response_model=TaskEventsResponse)
async def get_task_events(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    after_seq: int | None = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> TaskEventsResponse:
    """可观测事件历史，支持 after_seq 增量拉取。"""
    # 1. 校验任务存在
    # 2. 按 seq 升序返回至多 limit 条
    return await task_service.list_task_events(
        db, task_id, after_seq=after_seq, limit=limit
    )


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> TaskDetail:
    """详情页：任务元数据 + 自事件推导的 plan（若有）。"""
    # 1. 加载 tasks 行
    # 2. 取最近一次 plan_created 事件的 payload 作为 plan
    return await task_service.get_task_detail(db, task_id)


@router.patch("/{task_id}", response_model=TaskDetail)
async def patch_task(
    task_id: str,
    body: TaskPatch,
    db: AsyncSession = Depends(get_db),
) -> TaskDetail:
    """部分更新任务；当前支持取消未结束任务。"""
    return await task_service.patch_task(db, task_id, body)


@router.delete("/{task_id}", response_model=OperationOkResponse)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> OperationOkResponse:
    """删除已结束状态的任务及其事件；running/pending 返回 409。"""
    return await task_service.delete_task(db, task_id)
