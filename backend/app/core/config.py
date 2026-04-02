"""应用配置（与 Agent 四模块解耦的进程级设置）。"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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

    #: ReAct agent loop 安全轮次上限（异常死循环时兜底；正常由墙钟与停滞超时先触发）；环境变量 MAX_REACT_ITERATIONS
    max_react_iterations: int = 512

    #: ReAct 单次任务整段墙钟上限（秒）；超时终止；环境变量 REACT_AGENT_WALL_TIMEOUT_SEC
    react_agent_wall_timeout_sec: float = 1800.0

    #: ReAct 无有效进展判定：自上次「可解析且含 action/final_answer 的轮次」或「工具调用返回」起超过该秒数视为卡住并终止；环境变量 REACT_AGENT_STALL_TIMEOUT_SEC
    react_agent_stall_timeout_sec: float = 180.0

    #: 工具失败后继续尝试的上限：ReAct 为「连续工具失败」次数；Plan-Execute 为「每计划步骤内执行次数」；环境变量 MAX_TOOL_FAILURE_ATTPTS
    max_tool_failure_attempts: int = 3

    #: 注入 LLM 时单会话最多携带的最近消息条数（含当前用户消息；环境变量 SESSION_MEMORY_MAX_MESSAGES）
    session_memory_max_messages: int = 32

    #: 浏览器跨域来源，逗号分隔；需覆盖前端实际访问来源（localhost 与 127.0.0.1 视为不同源）
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    #: Tavily 搜索（内置 tavily_search 工具）；留空则不注册该工具；环境变量 TAVILY_API_KEY
    tavily_api_key: str | None = None

    #: Agent 文件类内置工具（read_file / write_file / list_directory）的根目录；留空为仓库根；相对路径相对仓库根解析；环境变量 AGENT_WORKSPACE_ROOT
    agent_workspace_root: str | None = None

    #: 是否注册 python_repl（任意代码执行，仅建议在受信环境开启）；环境变量 AGENT_ENABLE_PYTHON_REPL（true/false）
    agent_enable_python_repl: bool = True

    #: 单次 python_repl 工具整段代码墙钟上限（秒）；含其中 subprocess.run 阻塞时间；≤0 则用 120；环境变量 PYTHON_REPL_TIMEOUT_SEC
    python_repl_timeout_sec: float = 120.0

    #: 是否注册 shell（任意系统命令，默认关闭）；环境变量 AGENT_ENABLE_SHELL_TOOL（true/false）
    agent_enable_shell_tool: bool = False

    #: 单次 Shell 工具子进程墙钟上限（秒）；防止交互脚本或无输出挂死；≤0 则用内置默认 120；环境变量 SHELL_TOOL_TIMEOUT_SEC
    shell_tool_timeout_sec: float = 120.0

    # --- OpenAI 兼容与 LLM 超时/重试（规划、路由、执行共用）---
    #: OpenAI 兼容 API（留空则规划/回复走内置确定性逻辑，便于 CI）；环境变量 OPENAI_API_KEY
    openai_api_key: str | None = None
    #: 兼容网关 Base URL；环境变量 OPENAI_API_BASE
    openai_api_base: str | None = None
    #: 模型名；环境变量 OPENAI_MODEL
    openai_model: str | None = None
    #: 单次 LLM 请求超时（秒）；避免上游无响应时协程长期挂起；≤0 则不传入（用库默认）；环境变量 OPENAI_REQUEST_TIMEOUT
    openai_request_timeout: float = 120.0
    #: LLM 客户端重试次数（OpenAI SDK 内置，部分状态码可能不覆盖如 529）；环境变量 OPENAI_MAX_RETRIES
    openai_max_retries: int = 3
    #: 应用层对过载/限流/短暂 5xx 的总尝试次数（含首次）；环境变量 OPENAI_RETRY_MAX_ATTEMPTS
    openai_retry_max_attempts: int = 8
    #: 应用层重试初始等待（秒），指数退避；环境变量 OPENAI_RETRY_BASE_DELAY_SEC
    openai_retry_base_delay_sec: float = 1.5
    #: 应用层单次等待上限（秒）；环境变量 OPENAI_RETRY_MAX_DELAY_SEC
    openai_retry_max_delay_sec: float = 60.0

    #: 供应商上下文总窗口（输入+输出上限的保守估计）；小模型或网关报错时调低；环境变量 LLM_CONTEXT_WINDOW_TOKENS
    llm_context_window_tokens: int = 8192
    #: 为完成内容预留的 token，从窗口中扣除以得到输入预算；环境变量 LLM_RESERVED_COMPLETION_TOKENS
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
            return _REPO_ROOT.resolve()
        p = Path(raw)
        if p.is_absolute():
            return p.resolve()
        return (_REPO_ROOT / p).resolve()


@lru_cache
def get_settings() -> Settings:
    """返回进程内单例配置；单测可 ``get_settings.cache_clear()`` 强制重载。"""
    return Settings()
