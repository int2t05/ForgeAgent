"""FastAPI 应用入口：生命周期、全局异常处理、路由挂载、健康检查。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, close_db, init_db
from app.core.exceptions import AppHTTPException
from app.modules.memory.checkpointer import close_langgraph_checkpointer, open_langgraph_checkpointer
from app.modules.tools.registry import tool_registry
from app.modules.workflow.graph import (
    get_checkpoint_guard_ref,
    init_compiled_agent_graph,
    shutdown_compiled_agent_graph,
)
from app.services.task_service import drain_agent_background_tasks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan：启动时初始化 DB、工具快照与编译图；关闭时逆序释放。"""
    # 1. 启动时建表（阶段1）；后续可换 Alembic
    await init_db()
    # 2. 按 settings_kv 刷新工具注册表（内置 + MCP mock + Skills）
    async with AsyncSessionLocal() as session:
        await tool_registry.refresh(session)
        await session.commit()
    # 3. LangGraph checkpointer + 编译状态图（线程 id = task_id 时可断点续跑）
    settings = get_settings()
    checkpointer = await open_langgraph_checkpointer(settings)
    init_compiled_agent_graph(checkpointer)
    yield
    # 4. 先收敛后台 Agent（否则会话 close 与引擎 dispose / 客户端断开取消叠加易触发 aiosqlite「no active connection」）
    await drain_agent_background_tasks()
    # 5. 关闭 checkpoint 连接与图引用，再释放 ORM 池
    await close_langgraph_checkpointer(get_checkpoint_guard_ref())
    shutdown_compiled_agent_graph()
    await close_db()


app = FastAPI(
    title="ForgeAgent API",
    description="REST API：任务与会话、可观测执行、任务事件 SSE",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppHTTPException)
async def _app_http_handler(_request, exc: AppHTTPException) -> JSONResponse:
    """将业务异常序列化为统一 JSON 形状（detail + code），不再嵌套一层 detail。"""
    raw = exc.detail
    if isinstance(raw, dict):
        return JSONResponse(status_code=exc.status_code, content=raw)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(raw)},
    )


@app.exception_handler(RequestValidationError)
async def _validation_handler(_request, exc: RequestValidationError) -> JSONResponse:
    """将 Pydantic 校验错误收敛为 API 文档约定的 400 + VALIDATION_ERROR。"""
    errs = exc.errors()
    msg = str(errs[0].get("msg")) if errs else "参数错误"
    return JSONResponse(
        status_code=400,
        content={"detail": msg, "code": "VALIDATION_ERROR"},
    )


app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    """负载均衡或本地探活。"""
    return {"status": "ok"}
