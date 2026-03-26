"""数据访问层包：按资源拆分的异步仓储函数（无业务分支）。"""

from app.repositories.event_repository import append_event

__all__ = ["append_event"]
