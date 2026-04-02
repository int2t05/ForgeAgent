# ForgeAgent Agent 工具使用流程

## 一、整体架构

```
ToolItem (Schema)
       ↑
       | (list_tools_public)
ToolRegistry  ──> builtin_tools + mcp_tools
       |
       | (execute)
       v
builtin_executor.py  ──> LangChain BaseTool.ainvoke
     |
mcp_client.py  ──> MCP ClientSession.call_tool
```
（Settings「Skills 路径」仅用于 Planner 选择后在执行步注入各目录 `SKILL.md` 文本，不注册工具、不发起 HTTP。）

---

## 二、工具注册机制

### 2.1 核心数据结构

**文件**: `modules/tools/registry.py`

```python
class ToolItem(BaseModel):
    name: str                           # 工具唯一名称
    description: str                    # 工具描述
    source: Literal["builtin", "mcp"]  # 来源
    read_only: bool | None = None
    parameters: dict[str, Any] | None = None  # JSON Schema
    mcp_server_name: str | None = None
```

### 2.2 ToolRegistry 类

```python
class ToolRegistry:
    def __init__(self):
        tools = list_builtin_tools()
        self._tools: list[ToolItem] = tools
        self._by_name: dict[str, ToolItem] = {t.name: t for t in tools}

    # 合并规则：同名工具先声明者优先（内置 > MCP）
    def _merge(self, parts):
        seen = set()
        merged = []
        for group in parts:
            for t in group:
                if t.name in seen:
                    continue
                seen.add(t.name)
                merged.append(t)
        return merged

    # 刷新：每次 settings 变更时重建工具快照
    async def refresh(self, db: AsyncSession):
        settings = await get_settings_public(db)
        builtins = list_builtin_tools()
        mcp_part = await tools_from_mcp_settings(settings.mcp)
        merged = self._merge((builtins, mcp_part))
        self._tools = merged
        self._by_name = {t.name: t for t in merged}
```

---

## 三、工具执行流程

### 3.1 分派入口

**文件**: `modules/tools/registry.py`

```python
async def execute(self, name: str, args: dict | None = None) -> dict:
    item = self._by_name.get(name)
    if item is None:
        return {"ok": False, "error": f"未知工具: {name}"}

    if item.source == "builtin":
        return await execute_builtin(name, dict(args) if args else {})

    if item.source == "mcp":
        return await self._execute_mcp(item, dict(args) if args else {})

    return {"ok": False, "error": f"来源为 {item.source} 的工具尚未接入"}
```

### 3.2 内置工具执行

**文件**: `modules/tools/builtin_executor.py`

```python
async def execute_builtin(name: str, args: dict) -> dict:
    tool = builtin_lc_tools_by_name().get(name)
    if tool is None:
        return {"ok": False, "error": f"未实现的内置工具: {name}"}

    timeout_sec = _tool_timeout_sec(name, settings)
    try:
        async with asyncio.timeout(timeout_sec):
            data = await _ainvoke_builtin(tool, payload)
    except TimeoutError:
        return {"ok": False, "error": f"工具执行超时（{int(timeout_sec)}s）: {name}"}
    except ValidationError as e:
        return {"ok": False, "error": _tool_validation_error_message(e)}

    return {"ok": True, "data": data}
```

### 3.3 Pydantic 参数校验

```python
async def _ainvoke_builtin(tool: BaseTool, payload: dict) -> Any:
    schema_cls = getattr(tool, "args_schema", None)
    if isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
        validated = schema_cls.model_validate(payload)  # 校验
        canonical = validated.model_dump(mode="json")
        return await tool.ainvoke(canonical)
    return await tool.ainvoke(payload)
```

### 3.4 超时策略

```python
def _tool_timeout_sec(name: str, settings: Settings) -> float:
    if name == "shell":
        return max(5.0, float(settings.shell_tool_timeout_sec))
    if name == "python_repl":
        return max(5.0, float(settings.python_repl_timeout_sec))
    if name in {"tavily_search", "duckduckgo_search"}:
        return max(3.0, float(settings.tool_search_timeout_sec))
    if name in {"read_file", "write_file", "list_directory"}:
        return max(2.0, float(settings.tool_file_timeout_sec))
    return max(5.0, float(settings.tool_default_timeout_sec))
```

---

## 四、内置工具清单

| 工具                | 来源                   | 说明         |
| ------------------- | ---------------------- | ------------ |
| `tavily_search`     | LangChain Community    | 网页搜索     |
| `duckduckgo_search` | LangChain Community    | 网页搜索     |
| `read_file`         | LangChain Community    | 文件读取     |
| `write_file`        | LangChain Community    | 文件写入     |
| `list_directory`    | LangChain Community    | 目录列表     |
| `python_repl`       | LangChain Experimental | Python 执行  |
| `shell`             | 自建                   | 系统 Shell   |
| `list_tools`        | 自建                   | 工具列表查询 |

---

## 五、工具执行重试机制

**文件**: `modules/execution/tool_runner.py`

### 5.1 带重试的执行入口

```python
async def run_single_tool_with_retry(
    task_id: str,
    step_id: Any,
    tool_name: str,
    tool_args: dict,
    max_tool_tries: int,
    *,
    react_thought: str | None = None,
) -> tuple[bool, dict, list[dict]]:
```

### 5.2 重试循环

```python
for attempt in range(1, max_tool_tries + 1):
    # 1. 熔断前置检查
    try:
        breaker.before_call()
    except CircuitOpenError:
        # 记录失败事件并结束
        break

    # 2. 调用工具
    exec_out = await tool_registry.execute(tool_name, tool_args)

    # 3. 落库 tool_result
    await event_repository.append_event(...)

    if ok:
        breaker.record_success()
        final_ok = True
        break

    # 4. 失败：熔断记录 + 指数退避
    breaker.record_failure()
    if attempt < max_tool_tries:
        exp = min(max_delay, base_delay * (2 ** (attempt - 1)))
        jitter = 0.5 + random.random() * 0.5
        wait = min(max_delay, exp * jitter)
        await asyncio.sleep(wait)
```

### 5.3 指数退避公式

```
delay = min(max_delay, base_delay * 2^(attempt-1) * jitter)
jitter ∈ [0.5, 1.0)
```

---

## 六、熔断器机制

**文件**: `core/circuit_breaker.py`

### 6.1 三种状态

| 状态        | 说明                                     |
| ----------- | ---------------------------------------- |
| `CLOSED`    | 正常，允许调用                           |
| `OPEN`      | 熔断中，拒绝调用，超时后进入 `HALF_OPEN` |
| `HALF_OPEN` | 探测态，允许一个请求，失败则再开         |

### 6.2 配置

```python
@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 10      # 失败次数阈值
    recovery_timeout_sec: float = 60.0

    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
```

---

## 七、ReAct 循环中的工具调用

**文件**: `modules/execution/step_react_loop.py`

```python
while True:
    # 1. LLM 生成 thought + actions/final_answer
    msg = await ainvoke_with_retry(chat, messages, settings)
    text = lc_message_text(msg)
    messages.append(AIMessage(content=text))

    data = parse_react_round_json(text)
    invocations = extract_tool_invocations(data)
    fa = pick_final_answer(data)

    if invocations:
        # 2. 执行每个工具调用
        for tn, args in invocations:
            final_ok, last_exec, attempt_rows = await run_single_tool_with_retry(
                task_id, step_id, tn, args, max_tool_tries,
                react_thought=thought_round,
            )
            call_results.append({...})

            # 3. 追加 Observation 到消息
            messages.append(HumanMessage(
                content="Observation:\n" + observation_block
            ))
        continue  # 继续下一轮

    if fa:
        step_final = fa
        break
```

---

## 八、完整调用链路

```
LLM 输出工具调用
    │
    ▼
run_step_react_loop()
    │
    ▼
run_single_tool_with_retry()
    │
    ├─ 落库 tool_call 事件
    │
    ├─ 检查熔断器 (breaker.before_call)
    │       │
    │       ▼ (熔断开启则直接失败)
    │
    ├─ tool_registry.execute()
    │       │
    │       ├─ builtin → execute_builtin() → tool.ainvoke()
    │       │
    │       └─ mcp → mcp_client_manager.call_tool()
    │
    ├─ 落库 tool_result 事件
    │
    ├─ 成功 → breaker.record_success()
    │
    └─ 失败 → breaker.record_failure() → 指数退避 → 重试
```

---

## 九、Skill 目录与 `SKILL.md`（非工具）

- 在设置中配置 `skills_paths` 后，Planner 提示词会列出可选目录；规划 JSON 中每步可含 `skill_imports`（目录名或路径）。
- Actor 执行该步时，`skill_sources.skill_import_context_from_paths` 读取对应目录下 `SKILL.md`，作为额外 **HumanMessage** 注入 ReAct，**不**经过 `tool_registry.execute`，也**不**发起任何 Skill HTTP。

---

## 十、关键配置

| 配置项                                   | 默认值 | 说明            |
| ---------------------------------------- | ------ | --------------- |
| `tool_default_timeout_sec`               | 30     | 默认工具超时    |
| `shell_tool_timeout_sec`                 | 60     | Shell 工具超时  |
| `python_repl_timeout_sec`                | 30     | Python 执行超时 |
| `tool_search_timeout_sec`                | 10     | 搜索工具超时    |
| `tool_file_timeout_sec`                  | 5      | 文件操作超时    |
| `tool_retry_base_delay_sec`              | 0.05   | 重试基础延迟    |
| `tool_retry_max_delay_sec`               | 10     | 重试最大延迟    |
| `circuit_breaker_tool_failure_threshold` | 10     | 熔断失败阈值    |
| `circuit_breaker_tool_recovery_sec`      | 60     | 熔断恢复超时    |
