"""任务可观测事件 REST 模型（与 task_events 表语义对齐）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskEventItem(BaseModel):
    """单条事件：seq 为任务内顺序；payload 为解析后的对象。"""

    seq: int
    ts: datetime
    module: str
    kind: str
    payload: dict[str, Any] | None = None


class TaskEventsResponse(BaseModel):
    """GET /tasks/{id}/events 响应。"""

    events: list[TaskEventItem] = Field(default_factory=list)
