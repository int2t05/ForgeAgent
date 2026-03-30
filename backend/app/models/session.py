"""会话表 sessions（记忆：会话级上下文）。"""


from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Session(Base):
    """与 AsyncSession（SQLAlchemy 会话）区分：此为业务会话实体。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship( # type: ignore
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    # passive_deletes：删除会话时依赖 DB 的 ON DELETE CASCADE，避免 ORM 先把 task.session_id 置 NULL 触发 NOT NULL 错误
    tasks: Mapped[list["Task"]] = relationship(  # type: ignore
        "Task",
        back_populates="session",
        passive_deletes=True,
    )
