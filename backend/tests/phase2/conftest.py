"""阶段2 专用 fixture：在根 conftest 已设定 DATABASE_URL 的前提下，做表级重置与 TestClient。"""

import asyncio

import pytest

from app.database import engine
from app.main import app
from app.models.base import Base
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_db() -> None: # type: ignore
    """每个用例前重建表结构，保证 REST 用例无跨用例数据残留。"""
    async def reset() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield # type: ignore


@pytest.fixture
def client() -> TestClient: # type: ignore
    """同步 TestClient：触发 FastAPI lifespan（含 init_db），请求走 ASGI 栈。"""
    with TestClient(app) as c:
        yield c # type: ignore
