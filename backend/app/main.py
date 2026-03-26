"""FastAPI 应用入口：生命周期、全局异常处理、路由挂载、健康检查。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.database import AsyncSessionLocal, close_db, init_db
from app.exceptions import AppHTTPException
from app.tools.registry import tool_registry


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用进程启动与关闭时的资源初始化与释放。"""
    # 1. 启动时建表（阶段1）；后续可换 Alembic
    await init_db()
    # 2. 按 settings_kv 刷新工具注册表（内置 + MCP mock + Skills）
    async with AsyncSessionLocal() as session:
        await tool_registry.refresh(session)
        await session.commit()
    yield
    # 3. 关闭时释放数据库连接池
    await close_db()


app = FastAPI(
    title="ForgeAgent API",
    description="MVP REST + 可观测任务；SSE 见阶段5",
    lifespan=lifespan,
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
