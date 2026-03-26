"""应用配置（规划/记忆/工具/执行 之外的横切基础设施）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量与可选的 .env 加载；与仓库根 .env.example 中 DATABASE_URL 对齐。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./data/forgeagent.db"


def get_settings() -> Settings:
    """构造或读取进程内 Settings 单例使用的工厂（由调用方缓存策略决定）。"""
    return Settings()
