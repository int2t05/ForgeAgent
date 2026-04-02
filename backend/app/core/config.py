"""应用进程级配置（数据库、Agent、工具、HTTP、LLM）。

环境变量名与字段对应关系：Pydantic Settings 默认使用「字段名全大写」，
例如 ``database_url`` → ``DATABASE_URL``、``langgraph_checkpoint_sqlite_path`` →
``LANGGRAPH_CHECKPOINT_SQLITE_PATH``。加载顺序：仓库根 ``.env`` → ``backend/.env`` → 进程环境变量。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE_PATHS: tuple[str, ...] = tuple(
    str(p)
    for p in (_REPO_ROOT / ".env", _BACKEND_ROOT / ".env")
    if p.is_file()
)


class Settings(BaseSettings):
    """与仓库根 ``.env.example`` 条目对齐；未列出的变量若传入则 ``extra=ignore``。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATHS if _ENV_FILE_PATHS else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 数据库（ORM / tasks / sessions）---
    database_url: str = "sqlite+aiosqlite:///./forgeagent.db"

    # --- LangGraph 检查点（与 ORM 库文件分离）---
    langgraph_checkpoint_sqlite_path: str = "./db_checkpoints/langgraph_checkpoints.db"
    langgraph_checkpoint_postgres_uri: str | None = None

    # --- HTTP：CORS ---
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # --- Agent：规划 / 记忆 / 步骤内工具重试 / ReAct 预算 ---
    max_replan_attempts: int = 3
    session_memory_max_messages: int = 32
    session_blackboard_max_notes: int = 64
    max_tool_failure_attempts: int = 3
    max_react_rounds_per_step: int = 20
    react_max_tokens_per_step: int = 8000
    tool_default_timeout_sec: float = 30.0
    tool_search_timeout_sec: float = 10.0
    tool_file_timeout_sec: float = 5.0
    tool_retry_base_delay_sec: float = 0.5
    tool_retry_max_delay_sec: float = 8.0
    circuit_breaker_llm_failure_threshold: int = 5
    circuit_breaker_llm_recovery_sec: float = 60.0
    circuit_breaker_tool_failure_threshold: int = 10
    circuit_breaker_tool_recovery_sec: float = 60.0

    # --- 内置工具：工作区、搜索、REPL、Shell ---
    agent_workspace_root: str | None = None
    tavily_api_key: str | None = None
    agent_enable_python_repl: bool = True
    python_repl_timeout_sec: float = 120.0
    agent_enable_shell_tool: bool = False
    shell_tool_timeout_sec: float = 120.0

    # --- LLM：OpenAI 兼容客户端 ---
    openai_api_key: str | None = None
    openai_api_base: str | None = None
    openai_model: str | None = None
    openai_request_timeout: float = 120.0
    openai_max_retries: int = 3

    # --- LLM：应用层拥塞退避（ainvoke_with_retry）---
    openai_retry_max_attempts: int = 8
    openai_retry_base_delay_sec: float = 1.5
    openai_retry_max_delay_sec: float = 60.0

    # --- LLM：上下文预算（裁剪与会话摘要侧）---
    llm_context_window_tokens: int = 8192
    llm_reserved_completion_tokens: int = 1024

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors_origins(cls, v: str) -> str:
        return v.strip()

    @field_validator("llm_context_window_tokens")
    @classmethod
    def _min_context_window(cls, v: int) -> int:
        return max(512, int(v))

    @field_validator("llm_reserved_completion_tokens")
    @classmethod
    def _min_reserved_completion(cls, v: int) -> int:
        return max(1, int(v))

    @model_validator(mode="after")
    def _ensure_llm_budget(self) -> "Settings":
        """预留输出不得大于等于总窗口，否则收束为窗口的一小部分。"""
        w = int(self.llm_context_window_tokens)
        r = int(self.llm_reserved_completion_tokens)
        if r >= w:
            object.__setattr__(self, "llm_reserved_completion_tokens", max(128, w // 4))
        return self

    @property
    def llm_max_input_tokens(self) -> int:
        """输入侧可用 token 上限（窗口减去预留输出）。"""
        w = int(self.llm_context_window_tokens)
        r = int(self.llm_reserved_completion_tokens)
        return max(256, w - r)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_agent_workspace_path(self) -> Path:
        """解析文件工具允许读写的根目录（默认 monorepo 根）。"""
        raw = (self.agent_workspace_root or "").strip()
        if not raw:
            p = _REPO_ROOT.resolve()
        else:
            path = Path(raw)
            p = path.resolve() if path.is_absolute() else (_REPO_ROOT / path).resolve()
        # 自定义工作区常见为新目录；LangChain 文件工具初始化会访问 root_dir，缺失则 Windows 报 WinError 3。
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    """返回进程内单例配置；单测可 ``get_settings.cache_clear()`` 强制重载。"""
    return Settings()
