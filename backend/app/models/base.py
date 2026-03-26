"""声明式基类（任务/会话/事件等持久化模型的共同根基）。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 声明式映射基类（全 ORM 模型继承）。"""

    pass
