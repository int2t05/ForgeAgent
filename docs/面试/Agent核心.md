# Agent 核心模块面试题

## 1. Plan-Act-Learn 详解（含 RAG）

### Q: 三大节点职责？

| 节点 | 输入 | 输出 | 核心逻辑 |
|------|------|------|----------|
| **Planner** | user_message, blackboard, RAG | plan_steps | LLM 生成计划 JSON，自动检索 RAG 注入上下文 |
| **Actor** | plan_steps, user_message | summary, tool_trace | ReAct 循环执行，可显式调用 rag_search |
| **Learner** | tool_trace, outcome | blackboard_notes | LLM 生成反思 |

### Q: 状态定义 (AgentState)？

```python
# backend/app/modules/workflow/state.py

class AgentState(TypedDict, total=False):
    task_id: str
    session_id: str
    user_message: str

    # 规划相关
    replan_count: int
    max_replan_attempts: int
    plan_steps: list[dict[str, Any]]  # 生成的步骤列表
    current_step_index: int

    # 黑板 (跨任务共享)
    blackboard_notes: NotRequired[list[str]]

    # 执行相关
    act_context: NotRequired[dict[str, Any]]
    act_tool_trace: NotRequired[list[dict[str, Any]]]
    act_step_results: NotRequired[list[dict[str, Any]]]

    # 学习相关
    learn_reflection: NotRequired[str]
    learn_should_replan: NotRequired[bool]
    learn_final_answer: NotRequired[str]

    # 流程控制
    replan_requested: bool
    outcome: NotRequired[Literal["success", "failed"]]
    summary: NotRequired[str | None]
```

### Q: Planner 如何生成计划？

```python
# backend/app/modules/planning/nodes.py

async def plan_node(state: AgentState) -> dict:
    task_id = state["task_id"]
    user_message = state.get("user_message") or ""
    session_id = state.get("session_id") or ""

    # 1. 如果是重规划，递增计划版本
    if state.get("replan_requested"):
        new_version = await task_repository.bump_plan_version(db, task_id)
        out["replan_count"] = next_count

    # 2. 加载会话历史消息 (带 Token 预算控制)
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    chat_messages = await mgr.load_chat_messages(db, session_id=session_id, ...)

    # 3. 选择相关技能并注入上下文
    selected_skill_paths = await select_skills_for_planner(chat_messages, settings, ...)
    if selected_skill_paths:
        ctx = skill_import_context_from_paths(selected_skill_paths)
        chat_messages.append(HumanMessage(content="【Skill 上下文】\n\n" + ctx))

    # 4. 读取黑板要点 (来自上轮 Learn 的反思)
    notes = state.get("blackboard_notes") or []
    if notes:
        chat_messages.append(HumanMessage(content="【黑板要点】\n" + "\n".join(notes[-10:])))

    # 5. 调用 LLM 生成步骤
    steps = await plan_steps_with_llm(chat_messages, settings, ...)

    # 6. 持久化事件
    await event_repository.append_event(db, task_id, "planning", "plan_created", ...)

    return {
        "plan_steps": steps,
        "current_step_index": 0,
        "act_context": {},
        "act_tool_trace": [],
        "act_step_results": [],
    }
```

### Q: 计划 JSON 格式？

```json
{
  "steps": [
    {
      "id": "1",
      "title": "理解需求",
      "description": "分析用户输入和上下文"
    },
    {
      "id": "2",
      "title": "实现代码",
      "description": "编写并测试代码"
    }
  ]
}
```

**注意**：计划是抽象步骤，不含工具！

### Q: LangGraph 图结构？

```python
# backend/app/modules/workflow/graph.py

def build_agent_graph(...) -> StateGraph:
    builder = StateGraph(AgentState)

    # 添加节点
    builder.add_node("plan", plan)
    builder.add_node("act", act)
    builder.add_node("learn", learn)

    # 添加边
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "act")
    builder.add_edge("act", "learn")

    # 条件边: learn 之后根据状态决定路由
    builder.add_conditional_edges(
        "learn",
        route_after_learn,
        {"plan": "plan", "done": END},
    )

    return builder
```

**图结构**：
```
START ──▶ plan ──▶ act ──▶ learn ──┬──▶ plan (重规划)
                                    │
                                    └──▶ END (完成)
```

---

## 2. ReAct 循环

### Q: ReAct 循环流程？

```python
# backend/app/modules/execution/step_react_loop.py

async def execute_plan_step_react(
    task_id: str,
    step: dict,
    user_message: str,
    prior_tool_trace: list,
    tools: list[ToolItem],
    settings,
    max_tool_tries: int = 3,
    max_react_rounds: int = 20,
) -> dict:
    """每步执行完整的 ReAct 循环"""

    messages = [
        SystemMessage(content=REACT_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt)
    ]

    for round_idx in range(max_react_rounds):
        # 1. LLM 生成思考和行动
        msg = await ainvoke_with_retry(chat, messages, settings)
        text = lc_message_text(msg)
        messages.append(AIMessage(content=text))

        # 2. 解析 JSON
        data = parse_react_round_json(text)
        invocations = extract_tool_invocations(data)
        fa = pick_final_answer(data)

        # 3. 有工具调用？
        if invocations:
            for tn, args in invocations:
                result = await run_single_tool_with_retry(...)
                messages.append(HumanMessage(content=f"观察: {result}"))
            continue

        # 4. 有最终答案？
        if fa:
            return {"ok": True, "step_final_answer": fa}

    return {"ok": False, "error": "达到最大轮次"}
```

### Q: LLM 输出格式？

```json
// 工具调用
{
  "thought": "用户想要计算阶乘，我需要...",
  "action": "python_repl",
  "action_input": {"code": "def factorial(n): return 1 if n <= 1 else n * factorial(n-1)"}
}

// 最终回答
{
  "thought": "已完成阶乘函数",
  "final_answer": "阶乘函数已实现，可以传入任意正整数计算阶乘"
}
```

---

## 3. 工具执行

### Q: 工具执行带重试？

```python
# backend/app/modules/execution/tool_runner.py

async def run_single_tool_with_retry(
    task_id: str,
    tool_name: str,
    args: dict[str, Any],
    max_tries: int = 3,
) -> str:
    breaker = get_tool_circuit_breaker()

    for attempt in range(1, max_tries + 1):
        # 1. 熔断检查
        breaker.before_call()

        try:
            # 2. 执行工具
            result = await tool_registry.execute(tool_name, args)

            if result["ok"]:
                breaker.record_success()
                return json.dumps(result)

        except Exception as e:
            breaker.record_failure()
            if attempt < max_tries:
                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                await asyncio.sleep(delay)

    return json.dumps({"ok": False, "error": f"工具执行失败"})
```

### Q: 指数退避公式？

```
delay = min(max_delay, base_delay × 2^(attempt-1) × jitter)
jitter ∈ [0.5, 1.0)
```

示例（base=0.5s, max=10s）：
- attempt 1: 0.5 × 1 × 0.75 ≈ 0.375s
- attempt 2: 0.5 × 2 × 0.8 ≈ 0.8s
- attempt 3: 0.5 × 4 × 0.6 ≈ 1.2s

### Q: 内置工具有哪些？

| 工具 | 功能 | 超时 |
|------|------|------|
| `python_repl` | Python 执行 | 30s |
| `shell` | 系统命令 | 60s |
| `read_file` | 文件读取 | 5s |
| `write_file` | 文件写入 | 5s |
| `list_directory` | 目录列表 | 5s |
| `tavily_search` | 网页搜索 | 10s |
| `rag_search` | RAG 检索 | 10s |

---

## 4. 重规划机制

### Q: 何时触发重规划？

```python
# backend/app/modules/memory/learn.py

async def learn_node(state: AgentState) -> dict:
    max_replan = state.get("max_replan_attempts", 0)
    replan_count = state.get("replan_count", 0)
    can_replan = replan_count < max_replan
    failed = state.get("outcome") == "failed"

    # 调用 LLM 反思
    if is_llm_configured(settings) and not failed:
        data = parse_llm_json_object(...)
        should_replan = data.get("should_replan", False)
        final_answer = data.get("final_answer", "")

    # 判断是否重规划
    if failed or not can_replan:
        should_replan = False

    return {
        "replan_requested": should_replan,
        "learn_should_replan": should_replan,
        ...
    }

def route_after_learn(state: AgentState) -> Literal["plan", "done"]:
    if state.get("outcome") == "failed":
        return "done"
    if state.get("replan_requested"):
        return "plan"
    return "done"
```

### Q: 重规划 vs 重新执行？

| 场景 | 处理 |
|------|------|
| 步骤执行失败 | 当前步重试 |
| 步骤执行成功但效果不佳 | 重规划（回到 Planner） |
| 计划本身有问题 | 重规划 |
| 任务失败 | 结束 |

---

## 5. 记忆系统

### Q: 三层记忆架构？

```
┌─────────────────────────────────────────────────────────────────┐
│                    Session Blackboard                            │
│         (跨任务共享，Learner 反思要点，持久化到 sessions 表)        │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ 写入
┌─────────────────────────────────────────────────────────────────┐
│                    Agent State (运行时)                          │
│         (当前任务内的完整状态，包含 plan_steps, tool_trace 等)      │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ 持久化 checkpoint
┌─────────────────────────────────────────────────────────────────┐
│                    Checkpoint Saver                              │
│         (LangGraph 状态快照，支持服务重启后恢复)                   │
└─────────────────────────────────────────────────────────────────┘
```

### Q: Session Memory 加载流程？

```python
# backend/app/modules/memory/context.py

class SessionLLMContextManager:
    async def load_chat_messages(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        fallback_user_content: str,
        settings: Settings | None = None,
    ) -> list[BaseMessage]:
        # 1. 从 DB 加载最近 N 条
        rows = await message_repository.list_recent_messages(
            db, session_id, limit=self._max_messages
        )

        # 2. ORM → LangChain 消息
        msgs = session_messages_to_chat_messages(rows)

        # 3. 触发摘要压缩（>20 条）
        return await maybe_compress_chat_history(msgs, settings)
```

### Q: 对话摘要压缩流程？

```python
# backend/app/modules/memory/context.py

async def maybe_compress_chat_history(
    messages: list[BaseMessage],
    settings: Settings,
) -> list[BaseMessage]:
    """当条数超过阈值时，将较早消息压成一条摘要 HumanMessage"""
    thr = int(settings.session_summarize_when_over)
    if len(messages) <= thr:
        return messages

    keep_n = min(int(settings.session_summary_keep_recent), len(messages) - 1)
    old = messages[:-keep_n]
    recent = messages[-keep_n:]

    # 调用 LLM 生成摘要
    prompt = f"请用不超过 {ans_cap} 字的中文概括要点...\n\n" + "\n".join(lines)
    chat = build_chat_model(settings)
    resp = await ainvoke_with_retry(chat, [HumanMessage(content=prompt)], settings)

    summary = getattr(resp, "content", "")
    head = HumanMessage(content=f"[历史对话摘要]\n{summary}")
    return [head, *recent]
```

### Q: 黑板 vs 记忆区别？

| 概念 | 内容 | 生命周期 |
|------|------|----------|
| **Session Memory** | 会话历史消息 | 会话内 |
| **Blackboard** | 反思要点 | 跨任务 |

---

## 6. Token 管理

### Q: Token 截断策略？

```
1. 系统消息优先保留
2. 非系统消息自新向旧贪心装入
3. 若装不下，截断最旧消息
```

```python
def truncate_chat_messages_to_budget(
    chat: BaseChatModel | None,
    messages: Sequence[BaseMessage],
    *,
    max_input_tokens: int,
) -> list[BaseMessage]:
    # 1. 拆分系统消息与其余角色消息
    raw_sys = [m for m in msgs if isinstance(m, SystemMessage)]
    others = [m for m in msgs if not isinstance(m, SystemMessage)]

    # 2. 自新向旧贪心装入非系统消息
    kept_rev: list[BaseMessage] = []
    for msg in reversed(others):
        trial = sys_list + list(reversed(kept_rev + [msg]))
        if estimate_messages_tokens(chat, trial) <= budget:
            kept_rev.append(msg)
        else:
            break

    # 3. 截断最后一条消息确保预算
    if kept_rev:
        out = sys_list + list(reversed(kept_rev))
    else:
        room = max(32, budget - estimate_messages_tokens(chat, sys_list))
        out = sys_list + [_truncate_one_message(chat, others[-1], room)]

    return out
```

### Q: Token 计数优先级？

| 优先级 | 方法 | 精度 |
|--------|------|------|
| 1 | Chat 模型内置 `get_num_tokens_from_messages` | 最高 |
| 2 | tiktoken 精确计数 | 高 |
| 3 | 启发式估算 `len(content) // 3` | 低 |

### Q: tiktoken 计数公式？

```python
# OpenAI Chat API 格式开销
_TOKENS_PER_MESSAGE = 4      # 每条消息固定开销
_REPLY_PRIMING_TOKENS = 3   # 回复 priming

def count_messages_tokens(messages: list[BaseMessage], *, model: str | None) -> int:
    enc = encoding_for_chat_model(model)
    total = 0
    for msg in messages:
        total += _TOKENS_PER_MESSAGE  # 4
        role = _role_for_message(msg)  # system/assistant/user
        total += len(enc.encode(role))
        total += len(enc.encode(message_content_text(msg.content)))
    total += _REPLY_PRIMING_TOKENS  # 3
    return total
```

---

## 7. RAG 知识库

### Q: RAG 混合检索流程？

```
用户查询
    │
    ▼
┌─────────────────────────────────────────────┐
│           Hybrid Search (混合检索)            │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Vector Search  │  │   BM25 Search   │  │
│  │  (ChromaDB)     │  │  (关键字检索)    │  │
│  └────────┬────────┘  └────────┬────────┘  │
│           │                      │            │
│           └──────────┬───────────┘            │
│                      ▼                       │
│           ┌─────────────────────┐             │
│           │  RRF (倒数排名融合)  │             │
│           └──────────┬──────────┘             │
└──────────────────────┼───────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│           Reranker (重排序)                  │
│        Cohere / MiniLM Cross-Encoder         │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
                 Top-K 结果
```

### Q: BM25 公式？

```
BM25 Score = Σ IDF(qi) × (tf(qi, D) × (k1 + 1))
                        / (tf(qi, D) + k1 × (1 - b + b × |D|/avgdl))

其中:
- IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5))
- tf(qi, D) = 词项在文档中的出现次数
- |D| = 文档长度
- avgdl = 平均文档长度
- k1, b = 可调参数 (通常 k1=1.5, b=0.75)
```

### Q: RRF 融合公式？

```python
# 倒数排名融合 (Reciprocal Rank Fusion)
@staticmethod
def reciprocal_rank_fusion(
    rankings: list[list[tuple[int, float]]], k: int = 60
) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, (doc_id, score) in enumerate(ranking):
            if doc_id not in scores:
                scores[doc_id] = 0.0
            # RRF 公式: 1 / (k + rank)
            scores[doc_id] += 1.0 / (k + rank + 1)

    result = [(doc_id, score) for doc_id, score in scores.items()]
    result.sort(key=lambda x: x[1], reverse=True)
    return result
```

### Q: LCEL RAG Chain？

```python
# backend/app/modules/memory/rag.py

def get_rag_chain(rag: RagKnowledgeBase, llm: Any, **kwargs) -> Any:
    """构建 LCEL RAG Chain"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个有用的助手。基于以下检索到的上下文来回答...\n\n{context}"),
        ("human", "{question}"),
    ])

    def format_docs(docs: list) -> str:
        return "\n\n".join(doc.page_content for doc in docs)

    rag_chain = (
        {"context": rag.get_retriever() | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
    )
    return rag_chain
```
