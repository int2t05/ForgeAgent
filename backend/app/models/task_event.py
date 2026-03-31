"""任务事件 task_events（执行可观测：seq 与 planning/memory/tool/execution 对齐）。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.shared.utc_datetime import UtcDateTime


class TaskEvent(Base):
    """任务执行过程中追加的一条可观测事件（seq 在 task_id 维度单调递增）。"""

    __tablename__ = "task_events"
    __table_args__ = (
        # 联合唯一约束：同一任务内，task_id + seq 不能重复，确保事件序号不乱序
        UniqueConstraint("task_id", "seq", name="uq_task_events_task_id_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        nullable=False,
    )  # timestamp
    module: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="events")  # type: ignore
