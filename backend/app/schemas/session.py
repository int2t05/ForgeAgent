"""会话与消息相关请求/响应模型（对齐 docs/api/API.md）。"""

from pydantic import BaseModel, Field

from app.schemas.json_datetime import JsonUtcDatetime


class SessionCreate(BaseModel):
    """POST /sessions 请求体。"""

    title: str | None = None


class SessionCreateResponse(BaseModel):
    """POST /sessions 响应。"""

    session_id: str


class SessionSummary(BaseModel):
    """GET /sessions 列表单项。"""

    id: str
    title: str | None
    created_at: JsonUtcDatetime
    last_message_preview: str | None = Field(
        default=None,
        description="最后一条消息正文摘要（列表接口填充；无消息时为 null）。",
    )


class SessionListResponse(BaseModel):
    """GET /sessions 分页响应。"""

    items: list[SessionSummary] = Field(default_factory=list)
    total: int


class SessionDetail(BaseModel):
    """GET /sessions/{id} 与 PATCH 后的会话元数据。"""

    id: str
    title: str | None
    created_at: JsonUtcDatetime


class SessionUpdate(BaseModel):
    """PATCH /sessions/{id} 请求体。"""

    title: str | None = None


class MessageCreate(BaseModel):
    """POST /sessions/{id}/messages 请求体。"""

    role: str
    content: str


class MessageUpdate(BaseModel):
    """PATCH .../messages/{id} 请求体。"""

    content: str


class MessageOut(BaseModel):
    """单条会话消息的对外表示。"""

    id: int
    role: str
    content: str
    created_at: JsonUtcDatetime


class MessagesListResponse(BaseModel):
    """GET /sessions/{id}/messages 响应。"""

    messages: list[MessageOut] = Field(default_factory=list)


class SessionContextWindowItem(BaseModel):
    """``GET .../context`` 中单条窗口消息：库内角色与送入 LangChain 的等价表示。"""

    id: int
    role: str
    created_at: JsonUtcDatetime
    llm_type: str = Field(description="LangChain 消息类型：human / ai 等（与会话 system 降级规则一致）。")
    llm_content: str = Field(description="送入模型的正文（system 角色会加 [会话 system] 前缀）。")


class SessionContextSummaryMeta(BaseModel):
    """会话历史摘要策略元数据（仅说明配置；本接口不调用 LLM 生成摘要）。"""

    enabled: bool
    summarize_when_over: int
    keep_recent: int
    eligible: bool = Field(
        description="以当前窗口条数计，若运行时已配置 LLM 是否可能触发摘要（不检查密钥是否可用）。",
    )


class SessionContextTokenBudget(BaseModel):
    """窗口内消息的 token 粗估与配置预算（粗估与运行时 `llm_context_budget` 一致策略）。"""

    estimated_input: int = Field(description="对窗口内 LangChain 消息列表的估算输入 tokens。")
    llm_max_input_tokens: int
    llm_context_window_tokens: int
    llm_reserved_completion_tokens: int


class SessionContextResponse(BaseModel):
    """GET /sessions/{id}/context：供前端展示「当前会话进入 Agent/规划侧的上下文视图」。"""

    session_id: str
    blackboard_notes: list[str] = Field(default_factory=list)
    window: list[SessionContextWindowItem] = Field(default_factory=list)
    session_message_total: int = Field(description="该会话消息表中的总条数。")
    window_max_messages: int = Field(description="配置 `session_memory_max_messages`，即窗口最多包含的最近消息条数。")
    summary: SessionContextSummaryMeta
    tokens: SessionContextTokenBudget
