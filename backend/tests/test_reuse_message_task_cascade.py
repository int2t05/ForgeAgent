"""复用/编辑用户消息路径：按 source_user_message_id 或时间回退删除任务并级联事件。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — 注册 ORM
from app.models.base import Base
from app.models.message import Message
from app.models.session import Session as ChatSession
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.repositories import event_repository, task_repository


def _enable_sqlite_foreign_keys(engine: object) -> None:
    @event.listens_for(engine.sync_engine, "connect")  # type: ignore[attr-defined]
    def _fk(dbapi_conn: object, _connection_record: object) -> None:
        cur = dbapi_conn.cursor()  # type: ignore[union-attr]
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


@pytest.mark.asyncio
async def test_delete_tasks_by_source_message_id() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sid = "sess-1"
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t_keep = t0 - timedelta(hours=1)

    async with maker() as db:
        async with db.begin():
            db.add(ChatSession(id=sid, title=None))
            m1 = Message(session_id=sid, role="user", content="u1", created_at=t0)
            m2 = Message(
                session_id=sid,
                role="user",
                content="u2",
                created_at=t0 + timedelta(hours=1),
            )
            db.add(m1)
            db.add(m2)
            await db.flush()
            db.add(
                Task(
                    id="task-keep",
                    session_id=sid,
                    status="success",
                    plan_version=1,
                    source_user_message_id=m1.id,
                    created_at=t_keep,
                    updated_at=t_keep,
                )
            )
            db.add(
                Task(
                    id="task-drop",
                    session_id=sid,
                    status="success",
                    plan_version=1,
                    source_user_message_id=m2.id,
                    created_at=t0 + timedelta(days=1),
                    updated_at=t0 + timedelta(days=1),
                )
            )
            await db.flush()
            await event_repository.append_event(
                db, "task-drop", "execution", "e", "{}"
            )
            anchor_mid = m2.id

    async with maker() as db:
        async with db.begin():
            await task_repository.delete_tasks_for_branch_from_user_message(
                db,
                session_id=sid,
                anchor_message_id=anchor_mid,
                anchor_time=t0 + timedelta(hours=1),
            )

    async with maker() as db:
        rows = (await db.execute(select(Task).order_by(Task.id))).scalars().all()
        assert [r.id for r in rows] == ["task-keep"]
        ev = (await db.execute(select(TaskEvent))).scalars().all()
        assert ev == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_tasks_legacy_null_source_uses_created_at() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sid = "sess-2"
    t0 = datetime(2020, 6, 1, tzinfo=timezone.utc)
    keep_ts = t0 - timedelta(hours=1)

    async with maker() as db:
        async with db.begin():
            db.add(ChatSession(id=sid, title=None))
            m = Message(session_id=sid, role="user", content="u", created_at=t0)
            db.add(m)
            await db.flush()
            db.add(
                Task(
                    id="legacy-keep",
                    session_id=sid,
                    status="success",
                    plan_version=1,
                    source_user_message_id=None,
                    created_at=keep_ts,
                    updated_at=keep_ts,
                )
            )
            db.add(
                Task(
                    id="legacy-drop",
                    session_id=sid,
                    status="success",
                    plan_version=1,
                    source_user_message_id=None,
                    created_at=t0 + timedelta(minutes=1),
                    updated_at=t0 + timedelta(minutes=1),
                )
            )
            mid = m.id

    async with maker() as db:
        async with db.begin():
            await task_repository.delete_tasks_for_branch_from_user_message(
                db,
                session_id=sid,
                anchor_message_id=mid,
                anchor_time=t0,
            )

    async with maker() as db:
        rows = (await db.execute(select(Task))).scalars().all()
        assert [r.id for r in rows] == ["legacy-keep"]

    await engine.dispose()
