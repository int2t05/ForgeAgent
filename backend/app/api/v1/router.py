"""聚合 /api/v1 业务子路由（会话、任务、设置、工具）。"""

from fastapi import APIRouter

from app.api.v1 import sessions, settings, tasks, tools, workspace

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(sessions.router)
api_router.include_router(tasks.router)
api_router.include_router(settings.router)
api_router.include_router(tools.router)
api_router.include_router(workspace.router)
