"""FastAPI 依赖注入入口（请求级 DB 会话等）。"""

from app.core.database import get_db

__all__ = ["get_db"]
