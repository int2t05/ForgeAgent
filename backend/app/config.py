"""应用配置（规划/记忆/工具/执行 之外的横切基础设施）。"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量与可选的 .env 加载；与仓库根 .env.example 中 DATABASE_URL 对齐。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./data/forgeagent.db"

    #: Agent 单次任务内允许的重规划次数上限（与 DEVELOP_ORDER 阶段4 一致）
    max_replan_attempts: int = 3

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


def get_settings() -> Settings:
    """构造或读取进程内 Settings 单例使用的工厂（由调用方缓存策略决定）。"""
    return Settings()
