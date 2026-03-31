"""SQLite 异步连接与会话工厂。"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()
engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=False,
)


def _register_sqlite_pragma(eng: AsyncEngine) -> None:
    """若为 SQLite，则在每个新连接上启用外键约束（与 ORM ForeignKey 一致）。"""
    if not str(_settings.database_url).startswith("sqlite"):
        return

    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):  # noqa: ARG001
        """connect 钩子：执行 PRAGMA foreign_keys=ON。"""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_register_sqlite_pragma(engine)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """创建所有已注册 ORM 表（启动时 create_all；迁移可另接 Alembic）。"""
    import app.models  # noqa: F401

    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """应用关闭时释放连接池。"""
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends：单请求一个 AsyncSession，生命周期与 HTTP 请求对齐。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
