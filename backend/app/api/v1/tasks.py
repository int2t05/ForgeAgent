"""任务 REST（执行：列表/创建/详情/事件；SSE 流见阶段5）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.exceptions import AppHTTPException
from app.schemas.event import TaskEventsResponse
from app.schemas.task import TaskCreate, TaskCreateResponse, TaskDetail, TaskListResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
async def get_tasks(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="pending|running|success|failed|cancelled"),
) -> TaskListResponse:
    """仪表盘：分页列出任务，可按状态筛选。"""
    # 1. 校验 status 枚举（若传入）
    # 2. 查总数与当前页 items
    return await task_service.list_tasks_page(
        db, limit=limit, offset=offset, status=status
    )


@router.post("", response_model=TaskCreateResponse)
async def post_task(body: TaskCreate) -> TaskCreateResponse:
    """创建任务并异步执行（阶段2 为 Mock Agent）。"""
    # 1. 在独立事务中写入用户消息与 running 任务
    # 2. 提交后调度 asyncio 任务执行 Mock
    # 3. 返回 task_id 与 SSE 路径（流本身阶段5 可用）
    return await task_service.create_task_start_mock(
        body.session_id,
        body.user_message,
    )


@router.get("/{task_id}/events/stream")
async def get_task_events_stream(task_id: str) -> None:
    """阶段5 实现 SSE；此处占位以满足 OpenAPI 与 events_stream_path 一致。"""
    raise AppHTTPException(
        f"SSE 未实现（task_id={task_id}）：见开发阶段5",
        code="NOT_IMPLEMENTED",
        status_code=501,
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
