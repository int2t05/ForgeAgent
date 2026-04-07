# ForgeAgent TODO 清单

> 与当前仓库实现对齐；路径均以 `backend/app/` 为根。P0/P1 为建议优先级。

---

## 一、Agent 核心

### 1. [DONE] 工具真实执行（Actor 按步调用）

**现状**: `modules/execution/nodes.py` 中 `actor_node` 对计划步骤解析 `tool` / `args`，调用 `tool_registry.execute`，写入 `tool_call` / `tool_result` / `step_end`；支持 `max_tool_failure_attempts` 重试。

**后续可选**: 更丰富的工具参数校验、与 LangChain `bind_tools` 的计划一体生成。

**涉及文件**: `app/modules/execution/nodes.py`、`app/modules/tools/registry.py`

---

### 2. [DONE] Session Memory 注入 Planner

**现状**: `modules/planning/nodes.py` 使用 `SessionLLMContextManager`（`memory/context.py`）加载最近 `session_memory_max_messages` 条消息；黑板尾部要点以 `HumanMessage` 附加后再 `plan_steps_with_llm`。

**后续可选**: 摘要压缩、向量检索长期记忆（超出 MVP）。

**涉及文件**: `app/modules/planning/nodes.py`、`app/modules/memory/context.py`、`app/repositories/message_repository.py`

---

### 3. [DONE] LangGraph Checkpoint 持久化

**现状**: `app/main.py` lifespan 调用 `open_langgraph_checkpointer(settings)`，默认 `AsyncSqliteSaver` 写入 `LANGGRAPH_CHECKPOINT_SQLITE_PATH`（与 ORM 库分离）；`init_compiled_agent_graph(checkpointer)`；`task_service` 以 `thread_id = task_id` 执行 `astream`。关闭时 `close_langgraph_checkpointer` + `shutdown_compiled_agent_graph`。

**后续可选**: 生产默认 Postgres saver；与取消/中断联动的 `adelete_thread` 策略统一文档化。

**涉及文件**: `app/modules/workflow/checkpointer.py`、`app/modules/workflow/graph.py`、`app/main.py`

---

### 4. [DONE] Tool 参数 Schema 与规划一体

**现状**: 计划步骤为 JSON 结构，工具执行走注册表；内置工具使用 Pydantic schema 校验参数。

**目标**: 规划阶段可选 `llm.bind_tools` 或结构化输出，减少「计划与工具 shape 漂移」。

**涉及文件**: `app/modules/planning/llm.py`、`app/modules/tools/*`

---

### 5. [DONE] ToolContext 传递用户身份

**现状**: 通过 `app/shared/tool_context.py` 的 `ToolContext` 在异步环境中传递用户身份信息、会话 ID、任务 ID。

**涉及文件**: `app/shared/tool_context.py`、`app/modules/tools/builtin_executor.py`

---

### 6. [DONE] 工具参数校验防止幻觉

**现状**: 通过 `app/shared/tool_validation.py` 的 `ToolArgsValidator` 对工具参数进行校验，防止 LLM 幻觉调用工具。

**涉及文件**: `app/shared/tool_validation.py`、`app/modules/tools/builtin_executor.py`

---

## 二、工具生态

### 7. [DONE] MCP 真实 Transport（stdio / SSE）

**现状**: `McpClientManager`（`mcp_client.py`）维护 stdio / SSE 长连接池；`mcp_sources.py` 在 refresh 时真实拉取工具列表；`registry.execute` 对 `source=mcp` 的工具经 `McpClientManager.call_tool` 调用真实 Server；Actor 的可选工具已包含 MCP。mock transport 作为无外部 Server 时的降级路径保留。

**涉及文件**: `app/modules/tools/mcp_client.py`（新增）、`app/modules/tools/mcp_sources.py`、`app/modules/tools/registry.py`、`app/modules/execution/nodes.py`、`app/schemas/tools.py`、`app/main.py`

---

### 8. [DONE] Skill 目录与 `SKILL.md` 上下文（无 HTTP）

**现状**: 已移除 Skill HTTP 工具调用。`skill_sources.py` 仅提供 `skill_import_context_from_paths` 与 `resolve_planner_skill_imports`；Planner 在 `skills_paths` 白名单下为每步可选 `skill_imports`；执行步将对应目录的 `SKILL.md` 注入 ReAct **HumanMessage**。`ToolRegistry` 只合并内置 + MCP。

**涉及文件**: `app/modules/tools/skill_sources.py`、`app/modules/tools/registry.py`、`app/modules/planning/*`、`app/modules/execution/step_executor.py`

---

## 三、RAG 知识库

### 9. [DONE] RAG 知识库（混合检索 + Rerank）

**现状**: `modules/memory/rag.py` 实现完整的 RAG 系统：
- 文档分块（RecursiveCharacterTextSplitter）
- 向量化（OpenAI Embeddings 或本地 FakeEmbeddings）
- 混合检索（向量 + BM25）
- Rerank 重排序（Cohere 或本地 cross-encoder）

**涉及文件**: `app/modules/memory/rag.py`、`app/core/config.py`

### 10. [DONE] RAG 内置工具

**现状**: 内置 `rag_search` 和 `rag_ingest` 工具，支持：
- `rag_search`: 检索知识库
- `rag_ingest`: 摄入文档到知识库

**涉及文件**: `app/modules/tools/builtin_lc.py`

### 11. [DONE] RAG 与 Agent 工作流融合

**现状**: `modules/memory/rag_integration.py` 实现 RAG 与 Planner 的融合：
- 在 Plan 节点自动检索 RAG 知识库
- 将检索结果作为 HumanMessage 注入规划上下文
- 支持显式调用 `rag_search` 工具

**涉及文件**: `app/modules/memory/rag_integration.py`、`app/modules/planning/nodes.py`

---

## 四、人机交互

### 11. [TODO] Human-in-the-Loop 中断 / 审批

**现状**: 无 `interrupt()` 流程。

**目标**: 敏感步骤暂停等待人工 `Command(resume=…)`。

**涉及文件**: `app/modules/workflow/graph.py`、`app/modules/execution/nodes.py`、`app/api/v1/tasks.py`（扩展）

---

### 12. [DONE] LangGraph Streaming（节点级落库）

**现状**: `task_service._run_agent_graph_to_completion` 使用 `stream_mode="updates"`，每节点完成后压缩增量写入 `task_events`（`module=workflow`，`kind=node_update`）。SSE 仍从表内轮询增量推送。

**后续可选**: 合并写库频率、补充 `stream_mode` 其它通道。

---

## 五、观测与质量

### 13. [TODO] Task 取消机制（`cancelled` 与图中断对齐）

**现状**: `cancelled` 在状态枚举中定义；需确认 LangGraph 运行中与 PATCH 取消的协同（若尚未完全贯通，此项保持 TODO）。

**目标**: `PATCH /tasks/{id}` 取消后图中止（或协作式轮询停止），并写 `task_events` 说明。

**涉及文件**: `app/services/task_service.py`、`app/api/v1/tasks.py`

---

### 14. [TODO] LangSmith / 外部 Tracing

**现状**: 无。

**目标**: 可选接入 LangSmith 或 OpenTelemetry。

---

### 15. [TODO] REST API 自动化测试（可选）

**现状**: 以手工验收与 OpenAPI 联调为主。

**目标**: pytest 覆盖会话 / 任务 / 事件契约。

---

## 六、架构增强

### 16. [TODO] 多 Agent 编排（子图）

**现状**: 单图 Plan-Act-Learn。

**目标**: 子图作为节点（超出 MVP 时在 feature flag 或文档中单独里程碑）。

---

### 17. [TODO] Settings 密钥加密存储

**现状**: `PUT /settings` 拒绝敏感 key 片段；`settings_kv` 明文存非密钥配置。

**目标**: 若未来允许服务端存密钥，需加密 at rest。

---

### 18. [TODO] WebSocket 替代 SSE（可选）

**现状**: SSE + DB 轮询增量。

**目标**: 可选 WebSocket 降低延迟。

---

## 七、优先级汇总

| 优先级 | TODO                                |
| ------ | ----------------------------------- |
| P0     | 13. 任务取消与运行中协同（若仍缺口） |
| P1     | 11. Human-in-the-Loop               |
| ~~P1~~ | ~~4. 工具 Schema / 规划一体~~ (DONE) |
| ~~P1~~ | ~~5. ToolContext 传递~~ (DONE)      |
| ~~P1~~ | ~~6. 工具参数校验~~ (DONE)          |
| ~~P1~~ | ~~9. RAG 知识库~~ (DONE)            |
| ~~P1~~ | ~~10. RAG 内置工具~~ (DONE)         |
| ~~P1~~ | ~~11. RAG 工作流融合~~ (DONE)       |
| P2     | 15. 自动化测试                       |
| P3     | 14. LangSmith                       |
| P3     | 16. 多 Agent                        |
| P4     | 17. 密钥加密                        |
| P4     | 18. WebSocket                       |
