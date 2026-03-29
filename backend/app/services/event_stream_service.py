"""任务事件 SSE 生成器（执行 / 可观测：与 task_events 已提交行对齐）。

轮询式增量读取：只推送 seq > last_sent 的行，避免依赖未提交事务内的写入；
任务进入终态后若连续若干轮无新事件则结束流，便于客户端与反向代理释放连接。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime

from app.database import AsyncSessionLocal
from app.models.task_event import TaskEvent
from app.repositories import event_repository, task_repository

_TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})
_POLL_INTERVAL_SEC = 0.15
_STABLE_ROUNDS_BEFORE_CLOSE = 4


def _payload_to_dict(raw: str | None) -> dict | None:
    """将 payload_json 解析为 dict；空或非法则返回 None。"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _json_default(obj: object) -> str:
    """JSON 序列化：datetime → ISO。"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _event_row_to_payload(row: TaskEvent) -> dict:
    """与 GET /tasks/{id}/events 中单条事件字段一致（ts 为 ISO 字符串）。
    将 TaskEvent 数据库行转换为 API 响应格式的字典
    """
    # isoformat() 返回 ISO 8601 格式的字符串
    ts_val = row.ts.isoformat() if row.ts else None
    return {
        "seq": row.seq,
        "ts": ts_val,
        "module": row.module,
        "kind": row.kind,
        "payload": _payload_to_dict(row.payload_json),
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
) -> AsyncIterator[bytes]:  # 异步迭代器类型注解
    """按 seq 单调递增推送已持久化事件；终态任务「空转」若干轮后结束。
    轮询式 Server-Sent Events (SSE) 生成器，用于实时推送任务事件
    """
    last_seq = after_seq
    stable_empty_rounds = 0

    while True:
        async with AsyncSessionLocal() as db:
            #  1. 每轮打开短会话：读任务状态与 seq > last_seq 的事件批次。
            task = await task_repository.get_task_by_id(db, task_id)
            if task is None:
                return
            rows = await event_repository.list_events(
                db,
                task_id,
                after_seq=last_seq,
                limit=200,
            )
        # 2. 有新行则重置「终态稳定」计数并 yield SSE 帧。
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
        # 3. 无新行且任务已终态则递增稳定计数，达阈值后结束生成器。
        if task.status in _TERMINAL_STATUSES:
            stable_empty_rounds += 1
            if stable_empty_rounds >= _STABLE_ROUNDS_BEFORE_CLOSE:
                return
        else:
            stable_empty_rounds = 0
        # 4. 任务仍为 running/pending 时继续轮询（短睡眠），避免忙等。
        await asyncio.sleep(_POLL_INTERVAL_SEC)
