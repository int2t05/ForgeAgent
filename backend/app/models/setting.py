"""非密钥配置 settings_kv（工具/MCP 元数据等，不含密钥明文）。"""

from datetime import datetime

from sqlalchemy import Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.shared.utc_datetime import UtcDateTime


class SettingsKV(Base):
    """键值配置行：value_json 存序列化配置；不得存用户密钥明文。"""

    __tablename__ = "settings_kv"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
