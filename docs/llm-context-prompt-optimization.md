# ForgeAgent LLM 上下文与提示词优化方案

## 一、当前实现分析

### 1.1 现有上下文管理机制

**消息加载** (`session_context.py`):
- 从数据库加载最近 `session_memory_max_messages`（默认 32）条消息
- 直接按 id 倒序取出再反转，保证时间顺序
- system 角色消息被转换为 `HumanMessage` 带 `[会话 system]` 前缀

**黑板要点**（Planner 侧拼接，Learner / `session_blackboard.py` 维护）:
- 会话级持久化字段：`sessions.blackboard_notes_json`；规划前将尾部若干条笔记拼成单独的 `HumanMessage`，与历史消息一并交给规划 LLM（详见 `planning/nodes.py`）

**Token 估算** (`llm_context_budget.py`):
```python
# 启发式估算，精度较低
def estimate_messages_tokens(chat, messages) -> int:
    return len(content) // 3 + msgs * 4
```

**截断策略** (`llm_context_budget.py`):
- 先丢弃最早的历史消息（跳过 SystemMessage）
- 如果还超，就截断第一条消息（二分搜索找到合适长度）
- 添加尾部提示：`"\n\n[... 已省略部分内容以适配上下文窗口 ...]"`

### 1.2 现有问题

| 问题 | 影响 |
|------|------|
| **无摘要压缩** | 对话超长时直接截断，历史信息丢失 |
| **Token 估算不精确** | 启发式 `len//3` 可能偏差 20-30% |
| **System Prompt 硬编码** | 无法运行时动态调整，无法版本管理 |
| **无长期记忆机制** | 每次会话从零开始，无用户偏好记忆 |
| **无 Few-shot 示例** | 无法注入少样本学习能力 |

---

## 二、官方最佳实践

### 2.1 LangGraph 原生方案

#### SummarizationNode（对话摘要）

LangGraph 提供 `langmem.short_term.SummarizationNode` 专门处理对话历史压缩：

```python
from langgraph.checkpoint.memory import InMemorySaver
from langmem.short_term import SummarizationNode, RunningSummary
from langchain_core.messages.utils import count_tokens_approximately

# 配置摘要节点
summarization_node = SummarizationNode(
    token_counter=count_tokens_approximately,  # 精确计数
    model=summarization_model,
    max_tokens=256,              # 摘要最大 token 数
    max_tokens_before_summary=256, # 触发摘要的阈值
    max_summary_tokens=128,       # 单次摘要最大 token
)
```

#### MessagesState with Summary

```python
from langgraph.graph import MessagesState

class State(MessagesState):
    summary: str  # 追加 summary 字段
```

#### Checkpoint + Memory Store

```python
from langgraph.checkpoint.redis import RedisSaver
from langgraph.store.redis import RedisStore

# 状态持久化
graph = builder.compile(checkpointer=checkpointer, store=store)

# 运行时访问 store
async def call_model(state, runtime: Runtime[Context]):
    memories = await runtime.store.asearch(
        namespace=("memories", user_id),
        query=state["messages"][-1].content,
        limit=3
    )
```

### 2.2 Anthropic SDK 方案

#### Auto-Compaction（自动压缩）

```python
from anthropic import Anthropic

client = Anthropic()

runner = client.beta.messages.tool_runner(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    tools=[search, done],
    messages=[...],
    compaction_control={
        "enabled": True,
        "context_token_threshold": 5000  # 到达阈值时自动压缩
    }
)
```

#### 精确 Token 计数

```python
# 使用 SDK 精确计数，避免估算偏差
token_count = client.messages.count_tokens(
    model="claude-sonnet-4-5-20250929",
    messages=[...],
    system="..."
)
print(f"Input tokens: {token_count.input_tokens}")
```

#### Skills/Prompts 版本管理

```python
# 创建 prompt 版本
client.beta.skills.versions.create(
    skill_id="sk_xxx",
    params={
        "version_number": "1.0",
        "content": "<skill_definition_content>"
    }
)
```

---

## 三、优化方案

### 3.1 Tier 1: 基础优化（立即实施）

#### 1. 精确 Token 计数

**当前实现**:
```python
# 启发式估算，误差大
return len(content) // 3 + msgs * 4
```

**优化后**:
```python
# backend/app/core/llm_context_budget.py

from anthropic import Anthropic

class TokenCounter:
    def __init__(self, model: str):
        self._client = Anthropic()
        self._model = model

    def count_messages(self, messages: list[dict], system: str | None = None) -> int:
        params = {"model": self._model, "messages": messages}
        if system:
            params["system"] = system
        result = self._client.messages.count_tokens(**params)
        return result.input_tokens

# 全局实例
_token_counter: TokenCounter | None = None

def get_token_counter() -> TokenCounter:
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter(settings.openai_model)
    return _token_counter
```

**预期效果**: Token 计数精度提升到误差 <5%

---

#### 2. 提示词模块化 + 版本管理

**当前实现**: System Prompt 硬编码在各个模块

```
backend/app/agent/prompts/
├── __init__.py
├── framework_router.py   # FRAMEWORK_ROUTER_SYSTEM = "..."
├── planning.py          # build_planner_system_prompt()
└── react.py             # build_react_system_prompt()
```

**优化后**:

```python
# backend/app/agent/prompts/registry.py

from dataclasses import dataclass
from enum import Enum
from typing import Callable

class PromptVersion(Enum):
    V1 = "v1"
    V2 = "v2"

@dataclass
class PromptEntry:
    version: PromptVersion
    created_at: datetime
    content: str
    description: str

class PromptRegistry:
    def __init__(self):
        self._prompts: dict[str, list[PromptEntry]] = {}

    def register(self, name: str, entry: PromptEntry):
        if name not in self._prompts:
            self._prompts[name] = []
        self._prompts[name].append(entry)

    def get_latest(self, name: str) -> str | None:
        entries = self._prompts.get(name, [])
        if not entries:
            return None
        return max(entries, key=lambda e: e.created_at).content

    def get_by_version(self, name: str, version: PromptVersion) -> str | None:
        for entry in self._prompts.get(name, []):
            if entry.version == version:
                return entry.content
        return None

# 使用示例
registry = PromptRegistry()
registry.register("react_system", PromptEntry(
    version=PromptVersion.V1,
    created_at=datetime.now(),
    content=REACT_SYSTEM_V1,
    description="ReAct Agent 基础版本"
))
registry.register("react_system", PromptEntry(
    version=PromptVersion.V2,
    created_at=datetime.now(),
    content=REACT_SYSTEM_V2,
    description="ReAct Agent 优化版本 - 增加思考指导"
))
```

**数据库化版本存储**:

```sql
-- prompts 表
CREATE TABLE prompts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- "react_system", "planner"
    version VARCHAR(20) NOT NULL,       -- "v1", "v2"
    content TEXT NOT NULL,
    description TEXT,
    variables JSONB,                    -- 动态变量模板
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, version)
);

-- prompt_versions 表（历史记录）
CREATE TABLE prompt_audit_log (
    id SERIAL PRIMARY KEY,
    prompt_id INTEGER REFERENCES prompts(id),
    changed_at TIMESTAMP DEFAULT NOW(),
    change_type VARCHAR(20),            -- "create", "update", "rollback"
    changed_by VARCHAR(100)
);
```

---

### 3.2 Tier 2: 核心优化（短期实施）

#### 3. 对话历史摘要压缩

**新增摘要节点**:

```python
# backend/app/agent/nodes/summarization_node.py

from langgraph.types import Command
from langgraph.graph import MessagesState
from langmem.short_term import SummarizationNode, RunningSummary
from langchain_core.messages import RemoveMessage, HumanMessage, AIMessage

class AgentState(MessagesState):
    summary: str
    context: dict[str, RunningSummary]

# 初始化摘要节点
def create_summarization_node(model, token_counter):
    return SummarizationNode(
        token_counter=token_counter,
        model=model,
        max_tokens=256,
        max_tokens_before_summary=512,  # 512 tokens 后触发摘要
        max_summary_tokens=128,
    )

# 摘要判断逻辑
async def should_summarize(state: AgentState, settings: Settings) -> bool:
    if state.get("summary"):
        return False  # 已有摘要，不再摘要

    messages = state["messages"]
    total_tokens = await token_counter.count_messages(messages)

    return total_tokens > settings.summarize_threshold_tokens
```

**修改任务服务**:

```python
# backend/app/services/task_service.py

async def create_and_start(db, data: TaskCreate):
    # ... 现有逻辑 ...

    # 判断是否需要摘要
    if await should_summarize(current_state, settings):
        # 插入摘要节点
        state = await summarization_node.ainvoke(current_state)

    # 继续正常执行
    result = await graph.ainvoke(state)
```

#### 4. 动态 System Prompt

**当前实现**: 静态字符串拼接

```python
# 当前
def build_react_system_prompt(catalog_block: str) -> str:
    return (
        "你是 ReAct 智能体（Reason + Act）：每一步只输出一个 JSON 对象...\n"
        f"【工具目录】\n{catalog_block}"
    )
```

**优化后 - 模板引擎**:

```python
# backend/app/agent/prompts/template.py

from string import Template
from dataclasses import dataclass

@dataclass
class PromptVariables:
    tools_catalog: str
    user_context: str = ""           # 用户偏好/记忆
    session_summary: str = ""        # 对话摘要
    conversation_mode: str = "auto"  # auto/plan_execute/react

REACT_SYSTEM_TEMPLATE = Template("""你是 ReAct 智能体（Reason + Act）：每一步只输出一个 JSON 对象...

${user_context}
${session_summary}

【对话模式】${conversation_mode}

【工具目录】
${tools_catalog}

输出格式：
- 需调用工具：{"thought":"简要中文推理","action":"工具name","action_input":{...}}
- 可回答用户：{"thought":"简要中文推理","final_answer":"给用户的完整中文答复"}
""")

def build_react_prompt(vars: PromptVariables) -> str:
    return REACT_SYSTEM_TEMPLATE.substitute(
        user_context=f"【用户偏好】\n{vars.user_context}" if vars.user_context else "",
        session_summary=f"【对话摘要】\n{vars.session_summary}" if vars.session_summary else "",
        conversation_mode=vars.conversation_mode,
        tools_catalog=vars.tools_catalog,
    )
```

**动态注入上下文**:

```python
# session_context.py 增强

class SessionLLMContextManager:
    def __init__(self, max_messages: int, store: RedisStore | None = None):
        self._max_messages = max_messages
        self._store = store  # 长期记忆存储

    async def get_user_context(self, user_id: str) -> str:
        """从长期记忆获取用户偏好"""
        if not self._store:
            return ""

        memories = await self._store.asearch(
            namespace=("user_preferences", user_id),
            query="*",
            limit=5
        )
        if not memories:
            return ""

        return "\n".join([f"- {m.value['content']}" for m in memories])

    async def load_chat_messages(self, db, session_id: str, fallback_user_content: str):
        # ... 现有逻辑 ...

        # 获取对话摘要（如果存在）
        summary = await self._get_session_summary(db, session_id)

        # 获取用户上下文
        user_context = await self.get_user_context(user_id)

        return messages, {"summary": summary, "user_context": user_context}
```

---

### 3.3 Tier 3: 高级优化（中期实施）

#### 5. Few-shot 示例池

**示例池管理**:

```python
# backend/app/agent/prompts/few_shot.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class FewShotExample:
    category: str                    # "code", "search", "reasoning"
    input_text: str
    output_text: str
    description: str = ""

class FewShotPool:
    def __init__(self):
        self._examples: dict[str, list[FewShotExample]] = {}

    def add(self, example: FewShotExample):
        if example.category not in self._examples:
            self._examples[example.category] = []
        self._examples[example.category].append(example)

    def get_for_category(self, category: str, limit: int = 3) -> list[FewShotExample]:
        return self._examples.get(category, [])[:limit]

    def select_by_similarity(self, query: str, limit: int = 3) -> list[FewShotExample]:
        """基于关键词匹配选择最相关的示例"""
        query_lower = query.lower()
        scored = []
        for category, examples in self._examples.items():
            for ex in examples:
                score = sum(1 for kw in ex.input_text.lower().split() if kw in query_lower)
                scored.append((score, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:limit]]

# 初始化示例池
def init_few_shot_pool() -> FewShotPool:
    pool = FewShotPool()

    # 代码生成示例
    pool.add(FewShotExample(
        category="code",
        input_text="写一个 Python 函数计算斐波那契数列",
        output_text='```python\ndef fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)\n```'
    ))

    # 搜索类示例
    pool.add(FewShotExample(
        category="search",
        input_text="查找关于 React hooks 的最新文档",
        output_text='{"action": "web_search", "action_input": {"query": "React hooks documentation 2025"}}'
    ))

    return pool

# 使用
few_shot_pool = init_few_shot_pool()

def build_react_prompt_with_few_shot(vars: PromptVariables, query: str) -> str:
    base_prompt = build_react_prompt(vars)

    # 动态添加相关示例
    relevant_examples = few_shot_pool.select_by_similarity(query, limit=2)

    if relevant_examples:
        examples_section = "\n\n【参考示例】\n" + "\n".join([
            f"输入：{ex.input_text}\n输出：{ex.output_text}"
            for ex in relevant_examples
        ])
        return base_prompt + examples_section

    return base_prompt
```

#### 6. LangGraph Checkpoint + Memory Store 集成

**改造后的 Graph 编译**:

```python
# backend/app/agent/workflow/builder.py

from langgraph.checkpoint.redis import RedisSaver
from langgraph.store.redis import RedisStore
from langgraph.checkpoint.memory import InMemorySaver

class AgentGraphBuilder:
    def __init__(self, settings: Settings):
        self._checkpointer = RedisSaver.from_conn_string(settings.redis_url)
        self._store = RedisStore.from_conn_string(settings.redis_url)

    def compile(self):
        builder = StateGraph(AgentState)

        # 添加节点
        builder.add_node("router", self.router_node)
        builder.add_node("planner", self.planner_node)
        builder.add_node("executor", self.executor_node)
        builder.add_node("summarizer", self.summarization_node)  # 新增

        # 添加边
        builder.add_edge(START, "router")
        # ... 其他边 ...

        # 编译时注入 checkpointer 和 store
        return builder.compile(
            checkpointer=self._checkpointer,
            store=self._store
        )

    async def call_model(self, state: AgentState, runtime: Runtime[Context]):
        """带长期记忆的模型调用"""
        # 1. 从 store 获取用户记忆
        memories = await runtime.store.asearch(
            namespace=("memories", runtime.context.user_id),
            query=str(state["messages"][-1].content),
            limit=3
        )

        # 2. 构建增强 system prompt
        memory_context = "\n".join([m.value["data"] for m in memories])
        system_msg = f"{BASE_SYSTEM_PROMPT}\n\n【相关记忆】\n{memory_context}"

        # 3. 调用模型
        response = await self.model.ainvoke(
            [{"role": "system", "content": system_msg}] + state["messages"]
        )

        return {"messages": [response]}
```

#### 7. Anthropic Compaction Control

```python
# backend/app/core/llm_client.py

from anthropic import Anthropic

class LLMClient:
    def __init__(self, settings: Settings):
        self._client = Anthropic(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def invoke_with_compaction(
        self,
        messages: list[dict],
        system: str | None = None,
        max_input_tokens: int = 7168,
    ):
        """使用自动压缩的调用"""
        # 1. 先计算当前 token 数
        token_count = self._client.messages.count_tokens(
            model=self._model,
            messages=messages,
            system=system,
        )

        # 2. 如果接近阈值，启用压缩
        compaction_threshold = max_input_tokens * 0.8

        if token_count.input_tokens > compaction_threshold:
            # 使用更小的上下文
            truncated = self._truncate_messages(messages, max_input_tokens // 2)

            return await self._client.messages.create(
                model=self._model,
                messages=truncated,
                system=system,
                max_tokens=1024,
            )

        return await self._client.messages.create(
            model=self._model,
            messages=messages,
            system=system,
            max_tokens=1024,
        )
```

---

## 四、实施路线图

### Phase 1: 基础优化（1-2 周）

| 优化项 | 工作内容 | 预期效果 |
|--------|----------|----------|
| 精确 Token 计数 | 接入 `anthropic.count_tokens` | 截断精度提升，误差 <5% |
| Prompt 版本管理 | 数据库 + Registry 类 | Prompt 可追溯、可回滚 |
| 动态变量模板 | 引入 Template 机制 | System Prompt 动态化 |

### Phase 2: 核心优化（2-3 周）

| 优化项 | 工作内容 | 预期效果 |
|--------|----------|----------|
| 对话摘要压缩 | 接入 `SummarizationNode` | 长对话不再丢失历史 |
| 长期记忆存储 | Redis Store + User Context | 跨会话用户偏好记忆 |
| 动态 System Prompt | Context 注入记忆和摘要 | Prompt 随状态动态调整 |

### Phase 3: 高级优化（3-4 周）

| 优化项 | 工作内容 | 预期效果 |
|--------|----------|----------|
| Few-shot 示例池 | 分类示例 + 相似度匹配 | 特定任务质量提升 |
| Checkpoint 持久化 | Redis Checkpointer | 支持任务中断恢复 |
| Compaction Control | Anthropic SDK 特性 | 上下文自动管理 |

---

## 五、关键配置建议

```python
# backend/app/core/config.py 新增配置

class Settings:
    # Token 计数
    use_exact_token_count: bool = True          # 是否使用精确计数

    # 摘要配置
    enable_summarization: bool = True
    summarize_threshold_tokens: int = 4096      # 触发摘要的 token 数
    summary_max_tokens: int = 256               # 摘要最大 token 数

    # 长期记忆
    enable_long_term_memory: bool = True
    memory_search_limit: int = 3               # 记忆搜索返回条数

    # Few-shot
    enable_few_shot: bool = True
    few_shot_limit: int = 3                     # 最多注入示例数

    # Prompt 版本
    prompt_version: str = "v1"                 # 当前使用的 Prompt 版本
```

---

## 六、监控指标

```python
# metrics.py

LLM_CONTEXT_METRICS = {
    # Token 使用
    "llm_input_tokens_avg": "平均输入 token 数",
    "llm_input_tokens_p95": "P95 输入 token 数",
    "llm_truncation_rate": "消息被截断的比例",

    # 摘要
    "summarization_triggered_total": "触发摘要的次数",
    "summarization_tokens_saved": "通过摘要节省的 token 数",

    # 记忆
    "memory_hit_rate": "长期记忆命中率",
    "memory_retrieval_latency_ms": "记忆检索延迟",

    # Prompt
    "prompt_version_current": "当前使用版本",
    "prompt_rollbacks_total": "Prompt 回滚次数",
}
```

---

## 七、总结

| 层级 | 当前状态 | 优化后 |
|------|----------|--------|
| **Token 计数** | 启发式估算 (len/3) | 精确 API 计数 |
| **上下文压缩** | 简单截断 | SummarizationNode |
| **System Prompt** | 硬编码字符串 | 数据库 + 版本管理 |
| **长期记忆** | 无 | Redis Store |
| **Few-shot** | 无 | 示例池 + 相似度匹配 |
| **状态持久化** | 无 | Redis Checkpointer |

通过以上优化，项目的 LLM 上下文管理将达到生产级水平，支持：
- 无限长度对话（通过摘要压缩）
- 用户偏好跨会话记忆
- Prompt 灰度发布和快速回滚
- 精确的成本控制和监控
