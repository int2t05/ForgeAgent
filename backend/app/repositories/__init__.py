"""数据访问层入口（按资源分模块）。"""

from app.repositories.event_repository import append_event

__all__ = ["append_event"]
