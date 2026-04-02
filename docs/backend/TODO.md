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

**现状**: `modules/planning/nodes.py` 使用 `SessionLLMContextManager`（`memory/session_context.py`）加载最近 `session_memory_max_messages` 条消息；黑板尾部要点以 `HumanMessage` 附加后再 `plan_steps_with_llm`。

**后续可选**: 摘要压缩、向量检索长期记忆（超出 MVP）。

**涉及文件**: `app/modules/planning/nodes.py`、`app/modules/memory/session_context.py`、`app/repositories/message_repository.py`

---

### 3. [DONE] LangGraph Checkpoint 持久化

**现状**: `app/main.py` lifespan 调用 `open_langgraph_checkpointer(settings)`，默认 `AsyncSqliteSaver` 写入 `LANGGRAPH_CHECKPOINT_SQLITE_PATH`（与 ORM 库分离）；`init_compiled_agent_graph(checkpointer)`；`task_service` 以 `thread_id = task_id` 执行 `astream`。关闭时 `close_langgraph_checkpointer` + `shutdown_compiled_agent_graph`。

**后续可选**: 生产默认 Postgres saver；与取消/中断联动的 `adelete_thread` 策略统一文档化。

**涉及文件**: `app/modules/memory/checkpointer.py`、`app/modules/workflow/graph.py`、`app/main.py`

---

### 4. [TODO] Tool 参数 Schema 与规划一体（LangChain Tools）

**现状**: 计划步骤为 JSON 结构，工具执行走注册表；部分工具为内置 LangChain 封装。

**目标**: 规划阶段可选 `llm.bind_tools` 或结构化输出，减少「计划与工具 shape 漂移」。

**涉及文件**: `app/modules/planning/llm.py`、`app/modules/tools/*`

---

## 二、工具生态

### 5. [TODO] MCP 真实 Transport（stdio / SSE）

**现状**: `mcp_sources.py` 仍可能以 mock / 元数据为主（以代码为准）。

**目标**: 真实 MCP Client stdio 或 HTTP，与 `tool_registry.execute` 路由一致。

**涉及文件**: `app/modules/tools/mcp_sources.py`、`app/modules/tools/registry.py`

---

### 6. [TODO] Skill 工具执行框架

**现状**: Skills 多从 manifest 解析元数据。

**目标**: 可执行 Skill 协议（入口、权限、超时）。

**涉及文件**: `app/modules/tools/skill_sources.py`

---

## 三、人机交互

### 7. [TODO] Human-in-the-Loop 中断 / 审批

**现状**: 无 `interrupt()` 流程。

**目标**: 敏感步骤暂停等待人工 `Command(resume=…)`。

**涉及文件**: `app/modules/workflow/graph.py`、`app/modules/execution/nodes.py`、`app/api/v1/tasks.py`（扩展）

---

### 8. [DONE] LangGraph Streaming（节点级落库）

**现状**: `task_service._run_agent_graph_to_completion` 使用 `stream_mode="updates"`，每节点完成后压缩增量写入 `task_events`（`module=workflow`，`kind=node_update`）。SSE 仍从表内轮询增量推送。

**后续可选**: 合并写库频率、补充 `stream_mode` 其它通道。

---

## 四、观测与质量

### 9. [TODO] Task 取消机制（`cancelled` 与图中断对齐）

**现状**: `cancelled` 在状态枚举中定义；需确认 LangGraph 运行中与 PATCH 取消的协同（若尚未完全贯通，此项保持 TODO）。

**目标**: `PATCH /tasks/{id}` 取消后图中止（或协作式轮询停止），并写 `task_events` 说明。

**涉及文件**: `app/services/task_service.py`、`app/api/v1/tasks.py`

---

### 10. [TODO] LangSmith / 外部 Tracing

**现状**: 无。

**目标**: 可选接入 LangSmith 或 OpenTelemetry。

---

### 11. [TODO] REST API 自动化测试（可选）

**现状**: 以手工验收与 OpenAPI 联调为主。

**目标**: pytest 覆盖会话 / 任务 / 事件契约。

---

## 五、架构增强

### 12. [TODO] 多 Agent 编排（子图）

**现状**: 单图 Plan-Act-Learn。

**目标**: 子图作为节点（超出 MVP 时在 feature flag 或文档中单独里程碑）。

---

### 13. [TODO] Settings 密钥加密存储

**现状**: `PUT /settings` 拒绝敏感 key 片段；`settings_kv` 明文存非密钥配置。

**目标**: 若未来允许服务端存密钥，需加密 at rest。

---

### 14. [TODO] WebSocket 替代 SSE（可选）

**现状**: SSE + DB 轮询增量。

**目标**: 可选 WebSocket 降低延迟。

---

## 六、优先级汇总

| 优先级 | TODO |
|--------|------|
| P0 | 9. 任务取消与运行中协同（若仍缺口） |
| P1 | 4. 工具 Schema / 规划一体 |
| P1 | 5. MCP 真实 Transport |
| P1 | 7. Human-in-the-Loop |
| P2 | 6. Skill 执行框架 |
| P2 | 11. 自动化测试 |
| P3 | 10. LangSmith |
| P3 | 12. 多 Agent |
| P4 | 13. 密钥加密 |
| P4 | 14. WebSocket |
