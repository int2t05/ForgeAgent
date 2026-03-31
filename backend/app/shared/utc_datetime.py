"""与 SQLite 配合的日期时间列类型：库内存 UTC，读回为 timezone-aware UTC。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """等价于 DateTime(timezone=True)，但保证从 SQLite 读出时带 UTC tzinfo。

    SQLite 的 CURRENT_TIMESTAMP 为 UTC，驱动多返回 naive datetime；序列化为无时区 ISO 时，
    前端会按本地时区解析，在东八区会表现为「早 8 小时」。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
