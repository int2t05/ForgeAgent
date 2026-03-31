"""应用配置（与 Agent 四模块解耦的进程级设置）。"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 相对本文件定位 monorepo 根与 backend 根，避免依赖进程 CWD 才能读到 .env
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE_PATHS: tuple[str, ...] = tuple(
    str(p)
    for p in (_REPO_ROOT / ".env", _BACKEND_ROOT / ".env")
    if p.is_file()
)


class Settings(BaseSettings):
    """从固定路径 .env 与环境变量加载；与仓库根 .env.example 对齐。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATHS if _ENV_FILE_PATHS else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./forgeagent.db"

    #: LangGraph 检查点 SQLite 文件路径（相对仓库/工作目录；与 ORM 库分离）
    langgraph_checkpoint_sqlite_path: str = "./db_checkpoints/langgraph_checkpoints.db"

    #: 若设置则使用 Postgres 存检查点（需安装 optional ``checkpoint-postgres``）
    langgraph_checkpoint_postgres_uri: str | None = None

    #: Agent 单次任务内允许的重规划次数上限（与 DEVELOP_ORDER 阶段4 一致）
    max_replan_attempts: int = 3

    #: 注入 LLM 时单会话最多携带的最近消息条数（含当前用户消息；环境变量 SESSION_MEMORY_MAX_MESSAGES）
    session_memory_max_messages: int = 32

    #: 浏览器跨域来源，逗号分隔；需覆盖前端实际访问来源（localhost 与 127.0.0.1 视为不同源）
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    #: OpenAI 兼容 API（留空则规划/回复走内置确定性逻辑，便于 CI）；环境变量 OPENAI_API_KEY
    openai_api_key: str | None = None
    #: 兼容网关 Base URL；环境变量 OPENAI_API_BASE
    openai_api_base: str | None = None
    #: 模型名；环境变量 OPENAI_MODEL
    openai_model: str | None = None

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache  # 缓存函数结果
def get_settings() -> Settings:
    """进程内单例配置（与 FastAPI 官方 Settings 教程一致）。

    单测或需重载环境变量时可调用 ``get_settings.cache_clear()``。
    """
    return Settings()
