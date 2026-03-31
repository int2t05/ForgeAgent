"""与 SQLite 配合的日期时间列类型：库内存 UTC，读回为 timezone-aware UTC。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """等价于 DateTime(timezone=True)，但保证从 SQLite 读出时带 UTC tzinfo。

    SQLite 存盘为无时区字面值时按 UTC 理解；写入时将 aware 归一化到 UTC 再去 tz，列比较与
    CURRENT_TIMESTAMP 一致。REST 层见 ``schemas.json_datetime`` 对外统一带 Z。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if dialect.name == "sqlite":
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
