"""JSON 序列化：API 对外时间一律为带 Z 的 UTC ISO8601，避免前端把无时区串当本地解析。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def serialize_datetime_utc_z(dt: datetime) -> str:
    """将 datetime 转为带 Z 的 UTC ISO8601。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    micro = dt.microsecond
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if micro:
        frac = f".{micro:06d}".rstrip("0").rstrip(".")
        if frac:
            base += frac
    return f"{base}Z"


JsonUtcDatetime = Annotated[
    datetime,
    PlainSerializer(serialize_datetime_utc_z, when_used="json"),
]
