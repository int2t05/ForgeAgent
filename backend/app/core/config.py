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
    #: 规划 LLM 输出 JSON 解析或步骤校验失败时，最多完整调用轮数（每轮一次 ainvoke；含首轮）
    planner_parse_max_attempts: int = 3
    #: Learner 反思 JSON 解析失败或 reflection 为空时，最多完整调用轮数（每轮一次 ainvoke；含首轮）
    learner_parse_max_attempts: int = 3
    session_memory_max_messages: int = 32
    #: 条数超过 ``session_summarize_when_over`` 时将更早消息摘要为一条，保留最近 ``session_summary_keep_recent`` 条
    session_conversation_summary_enabled: bool = True
    session_summarize_when_over: int = 20
    session_summary_keep_recent: int = 10
    session_summary_line_max_chars: int = 400
    session_summary_max_answer_chars: int = 500
    session_blackboard_max_notes: int = 64
    max_tool_failure_attempts: int = 3
    max_react_rounds_per_step: int = 20
    react_max_tokens_per_step: int = 8000
    #: 单条 Observation（JSON）写入 LLM 前的最大字符数，防止工具大返回占满上下文
    react_tool_observation_max_json_chars: int = 12000
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
    #: 与网关模型总窗口对齐（如 MiniMax-M2.7 约 204_800；较小模型请在 .env 调低）
    llm_context_window_tokens: int = 204_800
    #: 单次请求为输出预留的 token，应从窗口中扣除后再算输入侧预算
    llm_reserved_completion_tokens: int = 8192
    # --- LLM：无 Chat 实例时用 tiktoken 精确计数（有实例则优先模型自带计数）---
    llm_use_exact_token_count: bool = True

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

    @field_validator("react_tool_observation_max_json_chars")
    @classmethod
    def _min_react_observation_cap(cls, v: int) -> int:
        return max(512, int(v))

    @field_validator("planner_parse_max_attempts")
    @classmethod
    def _min_planner_parse_attempts(cls, v: int) -> int:
        return max(1, int(v))

    @field_validator("learner_parse_max_attempts")
    @classmethod
    def _min_learner_parse_attempts(cls, v: int) -> int:
        return max(1, int(v))

    @model_validator(mode="after")
    def _ensure_llm_budget(self) -> "Settings":
        """预留输出不得大于等于总窗口，否则收束为窗口的一小部分。"""
        w = int(self.llm_context_window_tokens)
        r = int(self.llm_reserved_completion_tokens)
        if r >= w:
            object.__setattr__(self, "llm_reserved_completion_tokens", max(128, w // 4))
        return self

    @model_validator(mode="after")
    def _session_summary_bounds(self) -> "Settings":
        """摘要保留条数与触发阈值收束为可用组合。"""
        keep = max(1, int(self.session_summary_keep_recent))
        object.__setattr__(self, "session_summary_keep_recent", keep)
        thr = max(keep + 1, int(self.session_summarize_when_over))
        object.__setattr__(self, "session_summarize_when_over", thr)
        return self

    @property
    def llm_max_input_tokens(self) -> int:
        """应用层「输入截断/装历史」预算：窗口减去预留补全。

        与模型/API 公布的总上下文 ``llm_context_window_tokens`` 区分：后者为单次请求
        中 prompt 与生成共享的上限；本属性才是裁剪与装填历史时采用的上限（为回复预留
        ``llm_reserved_completion_tokens``）。若修改 .env 中对应两项，本值随之变为 窗口−预留。
        """
        w = int(self.llm_context_window_tokens)
        r = int(self.llm_reserved_completion_tokens)
        return max(256, w - r)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_agent_workspace_path(self) -> Path:
        """解析 Agent 文件工具与 shell 使用的根目录（显式配置优先，其次 env，否则仓库根）。"""
        from app.core.workspace_config import get_explicit_workspace_root

        # 1. 合并显式根（API 持久化）与 env 字段
        raw = (get_explicit_workspace_root() or self.agent_workspace_root or "").strip()
        # 2. 得到绝对路径（相对路径相对 monorepo 根）
        if not raw:
            p = _REPO_ROOT.resolve()
        else:
            path = Path(raw)
            p = path.resolve() if path.is_absolute() else (_REPO_ROOT / path).resolve()
        # 3. 确保目录存在，避免 LangChain 文件工具在 Windows 上访问不存在 root 失败
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    """返回进程内单例配置；单测可 ``get_settings.cache_clear()`` 强制重载。"""
    return Settings()
