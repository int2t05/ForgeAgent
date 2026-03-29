"""阶段4 专用 fixture：表级重置 + TestClient（与阶段2/3 一致）。"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.database import engine
from app.main import app
from app.models.base import Base


@pytest.fixture(autouse=True)
def _reset_db() -> None: # type: ignore
    """每个用例前重建表结构，隔离 Agent 运行时用例。"""
    async def reset() -> None:
        # 1. 释放连接池，避免 Windows 上 SQLite 在 drop_all 时仍被占用
        await engine.dispose()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield # type: ignore


@pytest.fixture
def client() -> TestClient: # type: ignore
    """同步 TestClient：触发 lifespan（init_db + tool_registry.refresh）。"""
    with TestClient(app) as c:
        yield c # type: ignore
