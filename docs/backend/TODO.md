# ForgeAgent TODO 清单

> 对标最新 LangGraph 特性，结合项目当前 Phase 0-8 路线图

---

## 一、Agent 核心（高优先级）

### 1. [TODO] 工具真实执行 (Executor 调用工具)

**现状**: `executor_node` 仅写入 `step_start` 事件，未调用任何工具。
**目标**: 将 plan_steps 转化为可执行工具调用。

```python
# 伪代码
async def executor_node(state: AgentState) -> dict:
    plan_steps = state.get("plan_steps", [])
    results = []
    for step in plan_steps:
        tool_name = step.get("tool")  # 需扩展 plan_steps schema
        args = step.get("args", {})
        result = await tool_registry.execute(tool_name, args)
        results.append(result)
        await event_repository.append_event(db, task_id, "execution", "step_end", {...})
    return {"step_results": results, "outcome": "success"}
```

**涉及文件**:
- `app/agent/nodes.py` — 重写 `executor_node`
- `app/tools/registry.py` — 新增 `execute(name, args)` 方法
- `app/modules/tools/builtin_lc.py` — 内置工具以 `langchain-community` / 可选 `langchain-tavily` 为准

---

### 2. [TODO] Session Memory 注入 LLM（多轮对话）

**现状**: `planner_node` 仅接收当前 `user_message`，无历史上下文。
**目标**: 将会话消息历史作为 ChatMessages 传给 LLM。

```python
# 伪代码
async def planner_node(state: AgentState) -> dict:
    session_id = state["session_id"]
    # 拉取历史消息（最近的 N 轮）
    history = await message_repository.get_recent(db, session_id, limit=20)
    messages = [SystemMessage(system_prompt)] + history + [HumanMessage(state["user_message"])]
    response = await llm.ainvoke(messages)
    plan = parse_plan(response)
    return {"plan_steps": plan}
```

**涉及文件**:
- `app/agent/nodes.py` — `planner_node` 扩展 history 注入
- `app/repositories/message_repository.py` — 新增 `get_recent(session_id, limit)`

---

### 3. [TODO] LangGraph Checkpoint 持久化（断点续执）

**现状**: AgentState 全程内存，进程崩溃任务丢失。
**目标**: 使用 SQLite/Postgres checkpointer 持久化图状态。

```python
# 伪代码（app/agent/graph.py）
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string(settings.database_url)
graph = builder.compile(checkpointer=checkpointer)

# 每次 avoke 时传入 config
config = {"configurable": {"thread_id": task_id}}
result = await graph.ainvoke(initial, config=config)
```

**涉及文件**:
- `app/agent/graph.py` — 注入 checkpointer
- `app/config.py` — 新增 `checkpointer_type` 配置项

---

### 4. [TODO] Tool 参数Schema绑定（LangChain Tool）

**现状**: 工具仅为元数据，无参数类型定义。
**目标**: 使用 `@tool` 装饰器或 `BaseTool` 定义真实工具。

```python
# 伪代码：优先使用 langchain-community 等官方集成
from langchain_community.tools import DuckDuckGoSearchRun

search = DuckDuckGoSearchRun()
llm_with_tools = llm.bind_tools([search])
```

**涉及文件**:
- `app/modules/tools/builtin_lc.py` — LangChain `BaseTool` 列表与 `list_tools`
- `app/agent/llm_client.py` — `plan_steps_with_llm` 使用绑定工具

---

## 二、工具生态

### 5. [TODO] MCP 真实 Transport（stdio / SSE）

**现状**: `tools_from_mcp_settings` 仅支持 mock 元数据。
**目标**: 实现真实 MCP Client stdio 调用。

```python
# 伪代码
async def tools_from_mcp_stdio(server_config: dict) -> list[ToolItem]:
    # 1. 启动子进程: mcp run <command>
    # 2. 通过 stdio 收发 JSON-RPC
    # 3. 解析 tools/list 响应
    # 4. 返回 ToolItem + 真实可执行句柄
    proc = await asyncio.create_subprocess_exec(
        cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    # 发送 initialize + tools/list
    ...
```

**涉及文件**:
- `app/tools/mcp_sources.py` — 新增 stdio 实现
- `app/tools/registry.py` — 工具执行时路由到 MCP transport

---

### 6. [TODO] Skill 工具执行框架

**现状**: `tools_from_skill_paths` 仅解析 manifest.json 元数据。
**目标**: 实现 Skill 真实调用协议（参考 FastAPI Skill）。

```python
# 伪代码
# manifest.json 扩展
{
  "name": "fastapi",
  "tools": [{"name": "create_endpoint", "description": "...", "parameters": {...}}],
  "entry": "main.py"  # 可执行入口
}

# Skill 执行
async def execute_skill_tool(skill_name: str, tool_name: str, args: dict):
    # 1. 加载 skill entry point
    # 2. 调用 skill 内部工具函数
    # 3. 返回标准化结果
```

---

## 三、人机交互

### 7. [TODO] Human-in-the-Loop 中断 / 审批

**现状**: 无。
**目标**: 敏感操作触发 `interrupt`，等待人工确认。

```python
# 伪代码
from langgraph.types import interrupt, Command

async def executor_node(state: AgentState) -> dict:
    for step in plan_steps:
        if step.get("requires_approval"):
            # 写入待审批事件
            await event_repository.append_event(...)
            # 中断图执行
            interrupt({
                "action": "approve_step",
                "step": step,
                "message": f"确认执行 {step['title']}？"
            })

# 恢复时
asyncio.create_task(graph.ainvoke(Command(resume={"approved": True}), config=config))
```

---

### 8. [TODO] LangGraph Streaming（节点级流式输出）

**现状**: 仅通过 SSE 轮询 task_events，无 LangGraph 原生流。
**目标**: 使用 `graph.astream` 配合 `stream_mode="updates"`。

```python
# 伪代码
async def run_agent_task_streaming(task_id: str, ...):
    config = {"configurable": {"thread_id": task_id}}
    async for chunk in graph.astream(initial, config, stream_mode=["updates", "messages"]):
        if chunk["type"] == "updates":
            # 实时推送节点增量
            await publish_sse_event(task_id, chunk)
```

**涉及文件**:
- `app/services/task_service.py` — 重写为流式执行

---

## 四、观测与质量

### 9. [TODO] Task 取消机制 (`cancelled` 状态)

**现状**: `cancelled` 在 `_VALID_TASK_STATUS` 中定义但无实际链路。
**目标**: 支持 `DELETE /tasks/{task_id}` 或 `POST /tasks/{task_id}/cancel`。

```python
# 伪代码
async def cancel_task(task_id: str):
    # 1. 更新状态为 cancelled
    # 2. 通过 checkpointer 的 checkpoint 机制通知图中断
    # 3. 写 task_events(kind=task_cancelled)
```

---

### 10. [TODO] LangSmith 可观测性集成

**现状**: 无。
**目标**: 接入 LangSmith tracing。

```python
# 伪代码
from langsmith import traceable

@traceable
async def planner_node(state: AgentState):
    ...
```

---

### 11. [TODO] REST API 自动化测试（可选）

**现状**: 仓库当前以手工验收与联调为主；无 `backend/tests/` 套件。
**目标**: 若恢复 pytest，覆盖会话创建/消息/任务 CRUD 等与 **`GET /openapi.json`**（及 `TECH_DESIGN.md` 数据模型）一致的契约。

---

## 五、架构增强

### 12. [TODO] 多 Agent 编排（子图嵌套）

**现状**: 单图 Planner → Executor。
**目标**: 支持子图作为节点（如专门的处理 Agent）。

```python
# 伪代码
builder.add_node("research_agent", research_subgraph)
builder.add_node("coding_agent", coding_subgraph)
```

---

### 13. [TODO] Settings 密钥管理（加密存储）

**现状**: `PUT /settings` 拒绝含敏感词的 key，但 settings_kv 明文存储。
**目标**: 对 `api_key` 类值加密后再入库。

```python
# 伪代码
from cryptography.fernet import Fernet

def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()
```

---

### 14. [TODO] WebSocket 替代 SSE（可选）

**现状**: SSE 轮询方式。
**目标**: 提供 WebSocket 通道降低延迟（可选）。

---

## 六、优先级汇总

| 优先级 | TODO | 对应 LangGraph 特性 |
|--------|------|--------------------|
| P0 | 1. 工具真实执行 | Tool Calling |
| P0 | 2. Session Memory | Message History |
| P0 | 3. Checkpoint 持久化 | Checkpointing |
| P1 | 4. Tool Schema 绑定 | LangChain Tools |
| P1 | 5. MCP 真实 Transport | MCP Integration |
| P1 | 7. Human-in-the-Loop | `interrupt()` |
| P2 | 6. Skill 执行框架 | Skill Protocol |
| P2 | 8. Streaming | `astream` |
| P2 | 9. Task 取消 | Cancellation |
| P3 | 10. LangSmith | Tracing |
| P3 | 11. Phase2 测试完善 | QA |
| P3 | 12. 多 Agent | Subgraphs |
| P4 | 13. 密钥加密 | Security |
| P4 | 14. WebSocket | Transport |
