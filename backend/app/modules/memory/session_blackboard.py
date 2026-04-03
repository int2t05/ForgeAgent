"""记忆域：会话级共享黑板（Learner 反思要点跨任务继承，落库 sessions.blackboard_notes_json）。"""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.repositories import session_repository

logger = logging.getLogger(__name__)


def decode_blackboard_json(raw: str | None) -> list[str]:
    """sessions.blackboard_notes_json → 字符串列表。"""
    if not (raw and str(raw).strip()):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if isinstance(x, str)]


def encode_blackboard_json(notes: list[str], max_notes: int) -> str:
    """截断后序列化；max_notes 至少为 1。"""
    m = max(1, int(max_notes))
    return json.dumps(notes[-m:], ensure_ascii=False)


def cap_blackboard_notes(notes: list[str], max_notes: int) -> list[str]:
    """图内黑板列表长度上限（与落库截断一致）。"""
    m = max(1, int(max_notes))
    return notes[-m:] if len(notes) > m else notes


async def read_session_blackboard(db: AsyncSession, session_id: str) -> list[str]:
    """读取会话黑板（无行则 []）。"""
    row = await session_repository.get_session_by_id(db, session_id)
    return decode_blackboard_json(row.blackboard_notes_json) if row else []


async def write_session_blackboard(
    db: AsyncSession,
    session_id: str,
    notes: list[str],
    *,
    max_notes: int,
) -> None:
    """将 LangGraph 状态中的黑板写回会话行（会话不存在则忽略）。"""
    row = await session_repository.get_session_by_id(db, session_id)
    if row is None:
        return
    row.blackboard_notes_json = encode_blackboard_json(notes, max_notes)


async def load_blackboard_seed(session_id: str) -> list[str]:
    """新任务启动时注入图初始 blackboard_notes。"""
    async with get_db_session() as db:
        return await read_session_blackboard(db, session_id)


async def flush_blackboard_from_graph_checkpoint(
    graph, config: dict, *, session_id: str
) -> None:
    """任务结束后把 checkpoint 终态黑板刷回会话，供下一任务继承。"""
    try:
        snap = await graph.aget_state(config)
        vals = dict(snap.values) if snap and snap.values else {}
        notes = vals.get("blackboard_notes")
        if not isinstance(notes, list) or not notes:
            return
        cap = get_settings().session_blackboard_max_notes
        async with get_db_session() as db:
            async with db.begin():
                await write_session_blackboard(
                    db, session_id, notes, max_notes=cap
                )
    except Exception:
        logger.debug(
            "session blackboard flush skipped for %s", session_id, exc_info=True
        )
