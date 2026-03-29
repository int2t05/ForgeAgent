"""阶段5：与阶段2 相同库重置策略，保证 SSE 与任务写入隔离。"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.database import engine
from app.main import app
from app.models.base import Base


@pytest.fixture(autouse=True)
def _reset_db() -> None:  # type: ignore[no-untyped-def]
    """每个用例前重建表结构。"""

    async def reset() -> None:
        await engine.dispose()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield  # type: ignore[unreachable]


@pytest.fixture
def client() -> TestClient:  # type: ignore[no-untyped-def]
    """同步 TestClient。"""
    with TestClient(app) as c:
        yield c  # type: ignore[misc]
