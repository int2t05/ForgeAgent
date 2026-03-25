"""SQLite 异步连接与会话工厂（记忆与任务持久化的数据层入口）。"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()
engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=False,
)


def _register_sqlite_pragma(eng: AsyncEngine) -> None:
    """SQLite 专有设置 外键约束启用函数。"""
    if not str(_settings.database_url).startswith("sqlite"):
        return

    # 开启 SQLite 外键约束
    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):  # noqa: ARG001
        """
        创建数据库连接时，设置 PRAGMA
        """
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_register_sqlite_pragma(engine)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)  # 创建会话


async def init_db() -> None:
    # 1. 加载全部 ORM，确保表注册到 Metadata
    import app.models  # noqa: F401

    from app.models.base import Base

    async with engine.begin() as conn:
        # 2. 建表；MVP 无 Alembic，启动时一次性 create_all
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：请求内会话，成功则提交，异常则回滚。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
