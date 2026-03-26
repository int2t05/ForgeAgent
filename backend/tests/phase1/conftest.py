"""阶段1：数据层测试专用 fixture（内存 SQLite + create_all）。"""

# Fixture 是 pytest 的依赖注入机制，用于在测试前提供可控的测试资源，测试结束后清理。
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base


@pytest_asyncio.fixture
async def async_engine():
    import app.models  # noqa: F401 — 注册全部表到 Metadata

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session
