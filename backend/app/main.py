from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_db, init_db


@asynccontextmanager  # 异步上下文管理器
async def lifespan(_app: FastAPI):
    # 1. 启动时建表（阶段1）；后续可换 Alembic
    await init_db()
    yield
    await close_db()


app = FastAPI(title="ForgeAgent API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
