"""阶段8 专用 fixture：与阶段2 相同库重置策略，供总验收 HTTP 用例隔离。"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.database import engine
from app.main import app
from app.models.base import Base


@pytest.fixture(autouse=True)
def _reset_db() -> None:
    """每个用例前重建表结构，避免跨用例数据干扰。"""
    async def reset() -> None:
        await engine.dispose()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield


@pytest.fixture
def client() -> TestClient:
    """同步 TestClient：触发 FastAPI lifespan（含 init_db）。"""
    with TestClient(app) as c:
        yield c
