# ForgeAgent Agent 框架优化方案

## 一、当前框架架构

### 1.1 整体拓扑

```
用户输入
    │
    ▼
┌─────────────────────────────────────────────────────┐
│              LangGraph Agent Workflow                │
│                                                      │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ Planner │───▶│  Actor  │───▶│ Learner │         │
│  └─────────┘    └─────────┘    └─────────┘         │
│       ▲                              │               │
│       │         ┌────────────────────┘              │
│       └─────────│ 条件分支: replan or done          │
│                 └──────────────────────────────────▶ END
└─────────────────────────────────────────────────────┘
```

**节点职责**：
| 节点 | 职责 | 关键输出 |
|------|------|----------|
| `planner_node` | 生成抽象计划步骤 | `plan_steps`, `replan_count` |
| `actor_node` | 遍历执行计划，ReAct 循环 | `actor_tool_trace`, `summary` |
| `learner_node` | 反思执行轨迹，决定是否重规划 | `blackboard_notes`, `replan_requested` |

**状态定义** (`modules/workflow/state.py`)：
```python
class AgentState(TypedDict, total=False):
    task_id: str
    session_id: str
    user_message: str
    replan_count: int
    max_replan_attempts: int
    plan_steps: list[dict]
    current_step_index: int
    blackboard_notes: list[str]
    actor_tool_trace: list[dict]
    replan_requested: bool
    outcome: str
    summary: str | None
    error_message: str | None
```

---

## 二、当前问题分析

### 2.1 框架层面问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **Planner 和 Actor 强耦合** | graph.py | 无法独立优化各节点 |
| **ReAct 循环无上限保护** | step_react_loop.py | 复杂任务可能无限循环 |
| **缺少 Human-in-the-Loop** | 全部节点 | 高风险操作无法人工介入 |
| **Actor 承担过多职责** | execution/nodes.py | 既是循环控制器又是执行器 |

### 2.2 错误处理问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **重试策略单一** | llm_retry.py | 所有错误同等对待，无差异化处理 |
| **工具重试无退避** | tool_runner.py | 瞬时失败立即重试，可能加剧拥堵 |
| **无熔断机制** | 全局 | 连续失败时仍持续调用 |
| **错误状态不区分** | task_service.py | 网络错误和业务错误混淆 |

### 2.3 工具系统问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **工具执行无超时** | builtin_executor.py | 慢工具阻塞整个 Agent |
| **MCP/Skill 未接入** | registry.py | 只有内置工具 |
| **无工具选择策略** | step_react_loop.py | 可能选择不合适的工具 |
| **Shell 工具安全风险** | builtin_executor.py | 任意命令执行 |

---

## 三、LangGraph 官方最佳实践

### 3.1 错误处理与重试策略

**分层重试策略**：

```python
from langgraph.types import RetryPolicy
from langgraph.graph import StateGraph

# 不同节点不同策略
builder.add_node(
    "query_database",
    query_database,
    retry_policy=RetryPolicy(
        retry_on=sqlite3.OperationalError,  # 只重试特定错误
        initial_interval=1.0,
        max_attempts=3,
    ),
)

builder.add_node(
    "call_model",
    call_model,
    retry_policy=RetryPolicy(
        max_attempts=5,
        retry_on=Exception,  # 模型调用更宽容
    ),
)
```

**错误分类处理**：

| 错误类型 | 处理策略 | 示例 |
|----------|----------|------|
| 瞬时错误 | 指数退避重试 | 网络超时、429 Rate Limit |
| LLM 可恢复 | 状态回送重试 | JSON 解析失败、工具调用失败 |
| 需人工介入 | interrupt 暂停 | 高风险操作、边界情况 |
| 未知错误 | 上抛 | 编程 bug、配置错误 |

### 3.2 Human-in-the-Loop 机制

**Interrupt 用法**：

```python
from langgraph.types import interrupt, Command

def send_email_tool(to: str, subject: str, body: str):
    """发送邮件（需审批）"""

    # 中断执行，等待人工批准
    response = interrupt({
        "action": "send_email",
        "to": to,
        "subject": subject,
        "body": body,
        "message": "确认发送此邮件？",
    })

    if response.get("action") == "approve":
        # 执行发送
        return send_email(to, subject, body)

    return "用户取消"
```

**时间旅行调试**：

```python
# 获取执行历史
history = list(graph.get_state_history(config))

# 从指定检查点重放
before_node = [s for s in history if s.next == ("node_name",)][-1]
replay_result = graph.invoke(None, before_node.config)

# Fork 并修改状态
fork_config = graph.update_state(before_node.config, {"value": ["modified"]})
```

### 3.3 状态管理与 Checkpoint

```python
from langgraph.checkpoint.redis import RedisSaver

# 持久化检查点
graph = builder.compile(checkpointer=RedisSaver.from_conn_string(REDIS_URL))

# 崩溃恢复
snap = await graph.aget_state(config)
if snap.next:  # 有未完成节点
    result = await graph.ainvoke(None, config)  # 继续执行
```

### 3.4 幂等性设计

```python
def node_a(state: State):
    # ✅ 使用 upsert（幂等）
    db.upsert_user(user_id=state["user_id"], status="pending")

    # ❌ 不要直接插入（非幂等）
    # db.insert_user(...)

    # 等待人工批准
    approved = interrupt("Approve?")

    return {"approved": approved}
```

---

## 四、优化方案

### 4.1 Tier 1: 框架结构优化（立即实施）

#### 1. ReAct 循环上限保护

**当前问题**：`step_react_loop.py` 循环无明确上限

```python
# 当前实现 - 无上限
while True:
    msg = await ainvoke_with_retry(chat, messages)
    # ... 解析和执行 ...
```

**优化后**：

```python
# modules/execution/step_react_loop.py

MAX_REACT_ROUNDS = 20  # 可配置

async def run_step_react_loop(..., max_rounds: int = MAX_REACT_ROUNDS):
    rounds = 0
    total_tokens_used = 0

    while True:
        rounds += 1

        # 1. 轮次保护
        if rounds > max_rounds:
            return {
                "ok": False,
                "error": f"ReAct 循环超过上限 ({max_rounds})",
                "calls": calls,
                "step_final_answer": None,
            }

        # 2. Token 预算保护
        if total_tokens_used > settings.max_tokens_per_step:
            return {
                "ok": False,
                "error": f"单步消耗 Token 超限",
                "calls": calls,
                "step_final_answer": None,
            }

        # 3. 执行 LLM 调用
        msg = await ainvoke_with_retry(chat, messages, settings)
        total_tokens_used += estimate_tokens(msg)

        # ... 解析和执行 ...
```

#### 2. 分层重试策略

**当前实现**：`llm_retry.py` 单一重试逻辑

```python
# 当前 - 所有错误同等对待
for attempt in range(max_attempts):
    try:
        return await chat.ainvoke(fitted)
    except Exception as e:
        wait = exponential_backoff(attempt)
```

**优化后 - 差异化重试**：

```python
# backend/app/core/llm_retry.py

from dataclasses import dataclass
from enum import Enum
from typing import Callable

class RetryStrategy(Enum):
    EXPONENTIAL_BACKOFF = "exponential"
    LINEAR_WAIT = "linear"
    IMMEDIATE_RETRY = "immediate"
    NO_RETRY = "none"

@dataclass
class ErrorRetryConfig:
    strategy: RetryStrategy
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    retry_on: Callable[[Exception], bool] = lambda _: True

# 按错误类型配置
ERROR_RETRY_CONFIGS: dict[str, ErrorRetryConfig] = {
    # 瞬时错误 - 指数退避
    "429": ErrorRetryConfig(RetryStrategy.EXPONENTIAL_BACKOFF, max_attempts=5),
    "429枕": ErrorRetryConfig(RetryStrategy.EXPONENTIAL_BACKOFF, max_attempts=5),
    "500": ErrorRetryConfig(RetryStrategy.EXPONENTIAL_BACKOFF, max_attempts=3),
    "503": ErrorRetryConfig(RetryStrategy.EXPONENTIAL_BACKOFF, max_attempts=3),

    # 网络错误 - 指数退避
    "APITimeoutError": ErrorRetryConfig(RetryStrategy.EXPONENTIAL_BACKOFF, max_attempts=4),

    # 上下文超限 - 立即重试（用截断后预算）
    "context_limit_exceeded": ErrorRetryConfig(RetryStrategy.IMMEDIATE_RETRY, max_attempts=1),

    # JSON 解析失败 - 快速重试
    "json_parse_error": ErrorRetryConfig(RetryStrategy.LINEAR_WAIT, max_attempts=2, base_delay=0.5),

    # 未知错误 - 不重试
    "unknown": ErrorRetryConfig(RetryStrategy.NO_RETRY, max_attempts=0),
}

def get_retry_config(error: Exception) -> ErrorRetryConfig:
    error_type = type(error).__name__
    error_message = str(error)

    # 精确匹配
    if error_type in ERROR_RETRY_CONFIGS:
        return ERROR_RETRY_CONFIGS[error_type]

    # HTTP 状态码匹配
    for key, config in ERROR_RETRY_CONFIGS.items():
        if key in error_message:
            return config

    return ERROR_RETRY_CONFIGS["unknown"]
```

#### 3. 工具执行超时控制

**当前实现**：`builtin_executor.py` 无超时

```python
# 当前
data = await tool.ainvoke(args)
```

**优化后**：

```python
# modules/tools/builtin_executor.py

import asyncio
from functools import partial

DEFAULT_TOOL_TIMEOUT = 30.0  # 默认 30 秒

async def execute_builtin_with_timeout(
    name: str,
    args: dict,
    timeout: float = DEFAULT_TOOL_TIMEOUT,
):
    tool = builtin_lc_tools_by_name().get(name)
    if tool is None:
        return {"ok": False, "error": f"未实现: {name}"}

    try:
        # 使用 asyncio.timeout 控制超时
        async with asyncio.timeout(timeout):
            data = await tool.ainvoke(args)
            return {"ok": True, "data": data}

    except asyncio.TimeoutError:
        return {"ok": False, "error": f"工具执行超时 ({timeout}s): {name}"}
    except ValidationError as e:
        return {"ok": False, "error": _tool_validation_error_message(e)}
    except Exception as e:
        return {"ok": False, "error": f"工具执行错误: {str(e)}"}

# 不同工具不同超时
TOOL_TIMEOUTS: dict[str, float] = {
    "tavily_search": 10.0,
    "duckduckgo_search": 10.0,
    "python_repl": 30.0,
    "shell": 60.0,
    "read_file": 5.0,
    "write_file": 5.0,
    "list_directory": 5.0,
}
```

---

### 4.2 Tier 2: 核心架构优化（短期实施）

#### 4. 引入 Human-in-the-Loop

**高风险工具拦截**：

```python
# backend/app/agent/tools/approvable.py

from langgraph.types import interrupt, Command
from typing import TypedDict

class ApprovalRequest(TypedDict):
    tool: str
    args: dict
    reason: str
    risk_level: str  # "low" | "medium" | "high" | "critical"

HIGH_RISK_TOOLS = {"shell", "write_file", "python_repl"}

async def execute_with_approval(
    tool_name: str,
    args: dict,
    task_id: str,
) -> dict:
    # 低风险工具直接执行
    if tool_name not in HIGH_RISK_TOOLS:
        return await execute_builtin_with_timeout(tool_name, args)

    # 高风险工具中断等待批准
    risk_level = "high" if tool_name == "shell" else "medium"

    approval_response = interrupt({
        "type": "tool_approval",
        "tool": tool_name,
        "args": args,
        "risk_level": risk_level,
        "task_id": task_id,
    })

    # 用户批准/修改
    if approval_response.get("action") == "approve":
        modified_args = approval_response.get("modified_args", args)
        return await execute_builtin_with_timeout(tool_name, modified_args)

    return {"ok": False, "error": "用户拒绝执行"}


# 在 tool_runner.py 中使用
async def run_single_tool_with_retry(..., require_approval: bool = False):
    if require_approval:
        result = await execute_with_approval(tool_name, args, task_id)
        if not result["ok"]:
            return False, result, []
        return True, result, []

    # 原有的重试逻辑
    ...
```

**前端批准界面**（API 扩展）：

```python
# backend/app/api/v1/approvals.py

@router.post("/approvals/{approval_id}/respond")
async def respond_to_approval(
    approval_id: str,
    action: Literal["approve", "reject"],
    modified_args: dict | None = None,
):
    # 存储批准结果到 Redis
    await redis.set(f"approval:{approval_id}", {
        "action": action,
        "modified_args": modified_args,
    })

    # 恢复 Agent 执行
    asyncio.create_task(resume_agent_after_approval(approval_id))
```

#### 5. Planner-Actor 解耦

**当前问题**：Actor 同时承担循环控制和步骤执行

**优化方案 - 引入 StepExecutor 节点**：

```python
# modules/execution/step_executor.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class StepResult:
    step_id: str
    status: Literal["success", "failed", "skipped"]
    result: dict | None
    error: str | None
    tokens_used: int

class StepExecutor:
    """单一步骤执行器（可复用）"""

    async def execute(
        self,
        step: dict,
        context: AgentState,
    ) -> StepResult:
        step_id = step["id"]
        title = step.get("title", step_id)

        # 1. 发送 step_start
        await event_repository.append_event(
            db, task_id, "execution", "step_start",
            {"step_id": step_id, "title": title}
        )

        # 2. 执行 ReAct 循环
        try:
            ok, calls, answer = await run_step_react_loop(
                step_id=step_id,
                messages=build_step_messages(context, step),
                settings=settings,
            )

            # 3. 发送 step_end
            await event_repository.append_event(
                db, task_id, "execution", "step_end",
                {"step_id": step_id, "ok": ok, "answer": answer}
            )

            return StepResult(
                step_id=step_id,
                status="success" if ok else "failed",
                result={"calls": calls, "answer": answer},
                error=None if ok else "ReAct loop failed",
                tokens_used=0,
            )

        except Exception as e:
            return StepResult(
                step_id=step_id,
                status="failed",
                result=None,
                error=str(e),
                tokens_used=0,
            )
```

**Actor 节点重构为循环控制器**：

```python
# modules/execution/nodes.py - 重构后

async def actor_node(state: AgentState) -> dict:
    plan_steps = state.get("plan_steps", [])
    current_idx = state.get("current_step_index", 0)
    executor = StepExecutor()

    results = []

    # 遍历执行（可并行化）
    for i in range(current_idx, len(plan_steps)):
        step = plan_steps[i]

        # 执行单一步骤
        result = await executor.execute(step, state)
        results.append(result)

        # 失败处理
        if result.status == "failed":
            return {
                "outcome": "failed",
                "error_message": f"步骤 {step['id']} 执行失败: {result.error}",
                "actor_tool_trace": results,
            }

    # 所有步骤完成，生成总结
    summary = await generate_summary(state, results)

    return {
        "actor_tool_trace": results,
        "summary": summary,
        "outcome": "success",
    }
```

#### 6. 智能计划验证（Plan-and-Validate）

```python
# modules/planning/validator.py

from pydantic import BaseModel, Field

class PlanValidationResult(BaseModel):
    is_feasible: bool
    issues: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)

async def validate_plan(plan_steps: list[dict], user_message: str) -> PlanValidationResult:
    """验证计划可行性"""

    validation_prompt = f"""用户请求：{user_message}

计划步骤：
{json.dumps(plan_steps, ensure_ascii=False, indent=2)}

请验证：
1. 各步骤是否可执行？
2. 步骤顺序是否合理？
3. 是否有遗漏的关键步骤？
4. 是否有不可行或危险的步骤？

返回 JSON：{{"is_feasible": bool, "issues": [], "suggested_fixes": []}}"""

    # 调用验证 LLM
    response = await ainvoke_with_retry(validation_llm, [HumanMessage(content=validation_prompt)])

    try:
        data = json.loads(extract_json_from_response(response))
        return PlanValidationResult(**data)
    except:
        return PlanValidationResult(is_feasible=True, issues=[], suggested_fixes=[])
```

**增强的 Planner 节点**：

```python
async def planner_node(state: AgentState) -> dict:
    # 1. 生成初始计划
    steps = await plan_steps_with_llm(chat_messages, settings)

    # 2. 计划验证（示例：可与特性开关组合）
    validation = await validate_plan(steps, state["user_message"])

    if not validation.is_feasible:
        await event_repository.append_event(
            db, task_id, "planning", "plan_validation_failed",
            {"issues": validation.issues}
        )

        if validation.suggested_fixes:
            steps = await refine_plan_with_feedback(
                steps, validation.suggested_fixes
            )

    # 3. 写计划事件
    await event_repository.append_event(
        db, task_id, "planning", "plan_created",
        {"steps": steps, "version": new_version}
    )

    return {
        "plan_steps": steps,
        "current_step_index": 0,
        "replan_count": new_version,
    }
```

---

### 4.3 Tier 3: 高级架构优化（中期实施）

#### 7. 工具选择策略

```python
# modules/tools/selector.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class ToolSelection:
    tool_name: str
    confidence: float  # 0-1
    reasoning: str

async def select_best_tool(
    user_message: str,
    available_tools: list[dict],
    context: AgentState,
) -> Optional[ToolSelection]:
    """基于语义相似度选择最合适的工具"""

    # 1. 提取用户意图关键词
    intent_keywords = extract_intent_keywords(user_message)

    # 2. 计算每种工具的匹配度
    scored_tools = []
    for tool in available_tools:
        name = tool["name"]
        description = tool.get("description", "")

        # 关键词匹配
        keyword_score = sum(
            1 for kw in intent_keywords
            if kw.lower() in description.lower()
        ) / max(len(intent_keywords), 1)

        # 语义相似度（可选：接入 Embedding）
        # semantic_score = await compute_similarity(user_message, description)

        # 综合得分
        confidence = min(1.0, keyword_score)  # + 0.5 * semantic_score

        scored_tools.append((confidence, tool["name"]))

    # 3. 返回最佳匹配
    scored_tools.sort(key=lambda x: x[0], reverse=True)

    if scored_tools and scored_tools[0][0] > 0.3:  # 阈值
        return ToolSelection(
            tool_name=scored_tools[0][1],
            confidence=scored_tools[0][0],
            reasoning=f"关键词匹配得分: {scored_tools[0][0]:.2f}",
        )

    return None  # 无合适工具
```

#### 8. 多 Agent 协作（可选扩展）

```python
# modules/multiagent/supervisor.py

class SupervisorAgent:
    """监督者 Agent - 负责任务分解和委派"""

    async def process(
        self,
        user_message: str,
        available_agents: dict[str, "SubAgent"],
    ) -> dict:
        # 1. LLM 分析任务类型
        task_type = await self.classify_task(user_message)

        # 2. 选择合适的 SubAgent
        if task_type == "code_generation":
            agent = available_agents["coder"]
        elif task_type == "web_search":
            agent = available_agents["researcher"]
        elif task_type == "file_operations":
            agent = available_agents["file_agent"]
        else:
            agent = available_agents["general"]

        # 3. 委派执行
        result = await agent.execute(user_message)

        return result
```

#### 9. 熔断机制

```python
# modules/core/circuit_breaker.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # 正常
    OPEN = "open"         # 熔断
    HALF_OPEN = "half_open"  # 半开

@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5       # 失败次数阈值
    recovery_timeout: float = 60.0   # 恢复超时（秒）
    success_threshold: int = 2       # 半开后成功阈值

    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _last_failure_time: datetime | None = None

    def record_success(self):
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                if elapsed > self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
            return False

        # HALF_OPEN - 允许一个测试请求
        return True


# 全局熔断器实例
LLM_CIRCUIT_BREAKER = CircuitBreaker(name="llm")
TOOL_CIRCUIT_BREAKER = CircuitBreaker(name="tools", failure_threshold=10)
```

---

## 五、实施路线图

### Phase 1: 基础加固（1-2 周）

| 优化项 | 工作内容 | 预期效果 |
|--------|----------|----------|
| ReAct 循环上限 | 添加 max_rounds 和 token 预算 | 防止无限循环 |
| 分层重试策略 | 差异化错误处理配置 | 减少无效重试 |
| 工具超时控制 | asyncio.timeout + 分工具超时 | 防止慢工具阻塞 |
| 熔断机制 | CircuitBreaker 类 | 快速失败保护 |

### Phase 2: 核心重构（2-4 周）

| 优化项 | 工作内容 | 预期效果 |
|--------|----------|----------|
| Human-in-the-Loop | interrupt + 审批 API | 高风险操作可干预 |
| Planner-Actor 解耦 | StepExecutor 提取 | 可独立测试/优化 |
| 计划验证 | Plan-and-Validate 模式 | 减少无效执行 |
| 智能工具选择 | 语义匹配 + 置信度 | 减少工具误用 |

### Phase 3: 高级特性（4-8 周）

| 优化项 | 工作内容 | 预期效果 |
|--------|----------|----------|
| 多 Agent 协作 | Supervisor + SubAgent | 支持复杂任务分解 |
| 时间旅行调试 | checkpoint replay | 便于调试 |
| 增量执行 | 基于 checkpoint 恢复 | 支持任务中断恢复 |

---

## 六、关键配置建议

```python
# backend/app/core/config.py 新增配置

class Settings:
    # ReAct 循环保护
    react_max_rounds: int = 20                 # 单步最大循环次数
    react_max_tokens_per_step: int = 8000     # 单步最大 token 消耗

    # 重试策略
    retry_exponential_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_max_attempts: int = 5

    # 工具超时（秒）
    tool_default_timeout: float = 30.0
    tool_shell_timeout: float = 60.0
    tool_search_timeout: float = 10.0

    # 熔断配置
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0

    # Human-in-the-Loop
    enable_approval_for_high_risk_tools: bool = True
    high_risk_tools: list[str] = ["shell", "write_file", "python_repl"]
```

---

## 七、监控与可观测性

```python
# metrics.py - Agent 专用指标

AGENT_METRICS = {
    # 循环指标
    "react_rounds_avg": "平均 ReAct 循环次数",
    "react_rounds_p99": "P99 ReAct 循环次数",
    "react_loops_aborted": "因超限中止的循环数",

    # 计划指标
    "plan_creation_latency_ms": "计划生成延迟",
    "plan_validation_failure_rate": "计划验证失败率",
    "replan_rate": "重规划率",

    # 工具指标
    "tool_execution_latency_ms": "工具执行延迟",
    "tool_timeout_rate": "工具超时率",
    "tool_error_rate": "工具错误率",
    "tool_selection_confidence_avg": "工具选择平均置信度",

    # 熔断指标
    "circuit_breaker_state": "熔断器状态",
    "circuit_breaker_trip_count": "熔断触发次数",

    # 人工介入
    "approval_requests_total": "审批请求总数",
    "approval_rejection_rate": "审批拒绝率",
    "approval_latency_ms": "审批响应延迟",
}
```

---

## 八、总结

| 层级 | 当前状态 | 优化后 |
|------|----------|--------|
| **循环保护** | 无上限 | max_rounds + token budget |
| **重试策略** | 单一指数退避 | 差异化分类重试 |
| **工具执行** | 无超时 | asyncio.timeout + 分工具配置 |
| **Human-in-the-Loop** | 无 | interrupt + 审批 API |
| **架构耦合** | Planner/Executor/Actor 耦合 | StepExecutor 解耦 |
| **计划验证** | 无 | Plan-and-Validate |
| **熔断机制** | 无 | CircuitBreaker |
| **工具选择** | 随机/顺序 | 置信度匹配 |
