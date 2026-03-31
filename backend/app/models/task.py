"""任务表 tasks（执行：单任务状态与计划版本）。"""

from datetime import datetime

from app.models.session import Session
from app.models.task_event import TaskEvent
from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.shared.utc_datetime import UtcDateTime


class Task(Base):
    """单条 Agent 执行任务的持久化状态（与会话、事件一对多）。"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default="pending",
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    #: 触发该任务的用户消息 id（用于编辑/重跑时按对话分支删除任务，不依赖时间比较）
    source_user_message_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped["Session"] = relationship("Session", back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(
        "TaskEvent",
        back_populates="task",
        cascade="all, delete-orphan",
    )
