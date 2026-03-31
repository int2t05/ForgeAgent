"""会话消息 messages（记忆：会话内 user/assistant/system）。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.shared.utc_datetime import UtcDateTime


class Message(Base):
    """会话内一条消息（user / assistant / system），用于会话级记忆。"""

    __tablename__ = "messages"
    # Mapped：SQLAlchemy 2.0 列类型与 Python 类型的显式绑定
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        nullable=False,
    )
    # 防止循环依赖
    session: Mapped["Session"] = relationship("Session", back_populates="messages")  # type: ignore
