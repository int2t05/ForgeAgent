"""LangGraph 检查点持久化：与业务 SQLite 分离的 checkpoint 存储。

默认使用 ``AsyncSqliteSaver``（官方推荐的异步 SQLite 后端）；可选 Postgres + 连接池
（需安装 ``checkpoint-postgres`` 可选依赖）。

参考：LangGraph Persistence / Add memory 文档。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiosqlite
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def delete_checkpoint_threads(settings: Settings, thread_ids: list[str]) -> None:
    """从 LangGraph checkpoint 存储删除与 ``thread_id``（即 task id）关联的表行。

    优先使用进程内已注入的 saver；若无（如部分测试），则按配置直连 SQLite 文件或 Postgres。
    """
    if not thread_ids:
        return

    from app.modules.workflow.graph import get_checkpoint_guard_ref

    saver = get_checkpoint_guard_ref()
    if saver is not None:
        for tid in thread_ids:
            await saver.adelete_thread(tid)
        return

    if settings.langgraph_checkpoint_postgres_uri:
        await _delete_threads_postgres_direct(
            settings.langgraph_checkpoint_postgres_uri, thread_ids
        )
    else:
        await _delete_threads_sqlite_file_direct(
            settings.langgraph_checkpoint_sqlite_path, thread_ids
        )


async def _delete_threads_sqlite_file_direct(
    db_path: str, thread_ids: list[str]
) -> None:
    """删除线程"""
    path = Path(db_path).resolve()
    if not path.is_file():
        return
    try:
        async with aiosqlite.connect(str(path)) as conn:
            for tid in thread_ids:
                t = str(tid)
                await conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (t,))
                await conn.execute("DELETE FROM writes WHERE thread_id = ?", (t,))
            await conn.commit()
    except aiosqlite.Error as exc:
        logger.warning("直连清理 LangGraph checkpoint SQLite 失败: %s", exc)


async def _delete_threads_postgres_direct(uri: str, thread_ids: list[str]) -> None:
    """使用直连 PostgreSQL 删除线程。"""
    try:
        import psycopg  # type: ignore
    except ImportError:
        logger.warning(
            "已配置 LANGGRAPH_CHECKPOINT_POSTGRES_URI 但未安装 psycopg，跳过 checkpoint 库清理"
        )
        return
    try:
        conn = await psycopg.AsyncConnection.connect(uri, autocommit=True)
        async with conn:
            async with conn.cursor() as cur:
                for tid in thread_ids:
                    t = str(tid)
                    await cur.execute(
                        "DELETE FROM checkpoints WHERE thread_id = %s", (t,)
                    )
                    await cur.execute(
                        "DELETE FROM checkpoint_blobs WHERE thread_id = %s", (t,)
                    )
                    await cur.execute(
                        "DELETE FROM checkpoint_writes WHERE thread_id = %s", (t,)
                    )
    except Exception as exc:  # noqa: BLE001 — 清理失败不应阻断会话删除
        logger.warning("直连清理 LangGraph checkpoint Postgres 失败: %s", exc)


async def open_langgraph_checkpointer(settings: Settings) -> BaseCheckpointSaver:
    """按配置创建已 ``setup`` 的异步 checkpointer，供 ``compile(checkpointer=...)`` 使用。"""
    # 1. Postgres：显式 URI 时使用连接池（生产可部署）
    if settings.langgraph_checkpoint_postgres_uri:
        return await _open_postgres_checkpointer(
            settings.langgraph_checkpoint_postgres_uri
        )
    # 2. 默认：独立 SQLite 文件，不与 SQLAlchemy 业务库混用同一连接
    return await _open_sqlite_checkpointer(settings.langgraph_checkpoint_sqlite_path)


async def _open_sqlite_checkpointer(db_path: str) -> AsyncSqliteSaver:
    """SQLite：确保目录存在，建立长连接并初始化表结构。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # path.resolve() — 转为绝对路径
    conn = await aiosqlite.connect(str(path.resolve()))  # 建立 aiosqlite 长连接
    saver = AsyncSqliteSaver(conn)  # checkpointer 实例
    await saver.setup()  # 初始化
    logger.info("LangGraph checkpoint SQLite ready at %s", path.resolve())
    return saver


async def _open_postgres_checkpointer(conn_string: str) -> Any:
    """Postgres：连接池 + AsyncPostgresSaver；依赖 ``pip install -e .[checkpoint-postgres]``。"""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
        from psycopg_pool import AsyncConnectionPool  # type: ignore
    except ImportError as exc:  # pragma: no cover - 环境未装可选依赖
        raise RuntimeError(
            "已设置 LANGGRAPH_CHECKPOINT_POSTGRES_URI，但未安装 Postgres checkpoint 依赖。"
            "请执行: pip install -e '.[checkpoint-postgres]'"
        ) from exc

    pool = AsyncConnectionPool(
        conninfo=conn_string,
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    saver = AsyncPostgresSaver(conn=pool)
    await saver.setup()
    logger.info("LangGraph checkpoint Postgres pool ready")
    return saver


async def close_langgraph_checkpointer(saver: BaseCheckpointSaver | None) -> None:
    """进程退出时释放 checkpointer 底层连接或连接池。"""
    if saver is None:
        return
    # conn 是 checkpointer 底层封装的数据库连接/连接池
    conn = getattr(saver, "conn", None)
    if conn is None:
        return
    try:
        from psycopg_pool import AsyncConnectionPool  # type: ignore
    except ImportError:
        AsyncConnectionPool = None  # type: ignore[misc,assignment]

    if AsyncConnectionPool is not None and isinstance(conn, AsyncConnectionPool):
        await conn.close()
        return
    # 从 conn 对象获取 close 属性（方法）
    closer = getattr(conn, "close", None)
    if closer is None:
        return
    maybe_coro = closer()  # 调用 conn.close
    if asyncio.iscoroutine(maybe_coro):  # 判断是否为协程
        await maybe_coro
