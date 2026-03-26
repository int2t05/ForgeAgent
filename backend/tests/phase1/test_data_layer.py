"""阶段1：数据层与 task_events.seq 语义（与 docs/DEVELOP_ORDER 阶段1、TECH_DESIGN §3 对齐）。"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Message, Session, SettingsKV, Task, TaskEvent
from app.repositories.event_repository import append_event


@pytest.mark.phase1
def test_metadata_registers_core_tables():
    """ORM 导入后 Metadata 含阶段1 五张表（无需数据库连接）。"""
    import app.models  # noqa: F401
    from app.models.base import Base

    expected = {"tasks", "task_events", "sessions", "messages", "settings_kv"}
    #  Base.metadata 注册了 五张核心表，无需连接数据库。
    assert expected <= set(Base.metadata.tables.keys())


@pytest.mark.phase1
@pytest.mark.asyncio  # 必要  需要这个标记来知道用事件表运行协程
async def test_create_all_sqlite_tables_exist(db_session):
    """内存库执行 create_all 后 sqlite_master 可见物理表。"""
    from sqlalchemy import text

    r = await db_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    )
    names = {row[0] for row in r.fetchall()}
    expected = {"tasks", "task_events", "sessions", "messages", "settings_kv"}
    assert expected <= names


@pytest.mark.phase1
@pytest.mark.asyncio
async def test_task_event_seq_monotonic_and_unique(db_session):
    """同一 task_id 下 seq 严格递增；违反 UNIQUE(task_id, seq) 应失败。"""
    sid, tid = str(uuid4()), str(uuid4())
    db_session.add(Session(id=sid, title="单元测试会话"))
    db_session.add(Task(id=tid, session_id=sid, status="running"))
    await db_session.commit()

    e1 = await append_event(db_session, tid, "planning", "plan_created", None)
    e2 = await append_event(db_session, tid, "execution", "step_start", "{}")
    e3 = await append_event(db_session, tid, "tool", "tool_call", None)
    await db_session.commit()

    assert e1.seq == 1 and e2.seq == 2 and e3.seq == 3

    dup = TaskEvent(
        task_id=tid,
        seq=1,
        module="execution",
        kind="error",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.phase1
@pytest.mark.asyncio
async def test_session_task_message_settings_chain(db_session):
    """sessions → tasks / messages → settings_kv 链式写入与外键可读。"""
    sid, tid = str(uuid4()), str(uuid4())
    db_session.add(Session(id=sid, title="链式"))
    db_session.add(Task(id=tid, session_id=sid, status="pending"))
    db_session.add(
        Message(session_id=sid, role="user", content="hello"),
    )
    db_session.add(
        SettingsKV(key="skills_paths", value_json="[]"),
    )
    await db_session.commit()

    m = await db_session.execute(select(Message).where(Message.session_id == sid))
    # m.scalar_one() 从 Result 中提取单个标量值（这里是 Message 对象本身）
    assert m.scalar_one().content == "hello"
