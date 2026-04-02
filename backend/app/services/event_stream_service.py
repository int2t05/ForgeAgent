"""任务事件 SSE 生成器（执行 / 可观测：与 task_events 已提交行对齐）。

轮询式增量读取：只推送 seq > last_sent 的行，避免依赖未提交事务内的写入；
任务进入终态后若连续若干轮无新事件则结束流，便于客户端与反向代理释放连接。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime

from app.core.database import AsyncSessionLocal
from app.schemas.json_datetime import serialize_datetime_utc_z
from app.shared.payload import payload_json_to_dict
from app.models.task_event import TaskEvent
from app.repositories import event_repository, task_repository

_TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})
_POLL_INTERVAL_SEC = 0.1
_STABLE_ROUNDS_BEFORE_CLOSE = 4


def _json_default(obj: object) -> str:
    """JSON 序列化：datetime → UTC Z（与 REST 一致）。"""
    if isinstance(obj, datetime):
        return serialize_datetime_utc_z(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _event_row_to_payload(row: TaskEvent) -> dict:
    """与任务事件 REST 列表单条字段一致（ts 为 ISO 字符串）。"""
    return {
        "seq": row.seq,
        "ts": serialize_datetime_utc_z(row.ts) if row.ts else None,
        "module": row.module,
        "kind": row.kind,
        "payload": payload_json_to_dict(row.payload_json),
    }


def _format_sse_message(*, event: str, event_id: int, data: dict) -> bytes:
    """封装一条 SSE 消息（id / event / data 与 docs/api/API.md 一致）。"""
    payload = json.dumps(data, ensure_ascii=False, default=_json_default)
    lines = [
        f"id: {event_id}",
        f"event: {event}",
        f"data: {payload}",
        "",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


async def iter_task_event_sse(
    task_id: str,
    *,
    after_seq: int,
) -> AsyncIterator[bytes]:
    """按 seq 单调递增推送已提交行；终态任务空转若干轮后结束。"""
    last_seq = after_seq
    stable_empty_rounds = 0

    async with AsyncSessionLocal() as db:
        while True:
            # 1. 读任务状态并拉取 seq 大于游标的已提交事件批次（整段流复用同一连接）
            task = await task_repository.get_task_by_id(db, task_id)
            if task is None:
                return
            rows = await event_repository.list_events(
                db,
                task_id,
                after_seq=last_seq,
                limit=200,
            )
            # 2. 有新事件则推送 SSE 并重置「无新事件」计数
            if rows:
                stable_empty_rounds = 0
                for row in rows:
                    data = _event_row_to_payload(row)
                    yield _format_sse_message(
                        event=row.kind,
                        event_id=row.seq,
                        data=data,
                    )
                    last_seq = row.seq
                await asyncio.sleep(_POLL_INTERVAL_SEC)
                continue
            # 3. 无新事件：终态任务在连续空转多轮后结束流；否则继续轮询
            if task.status in _TERMINAL_STATUSES:
                stable_empty_rounds += 1
                if stable_empty_rounds >= _STABLE_ROUNDS_BEFORE_CLOSE:
                    return
            else:
                stable_empty_rounds = 0
            await asyncio.sleep(_POLL_INTERVAL_SEC)
