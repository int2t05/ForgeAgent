# ForgeAgent 提示词优化方案

## 一、当前状态

### 1.1 提示词分布

| 节点 | 文件 | 内容 |
|------|------|------|
| 外部会话（全栈编码） | `M-prompts/M9CODESTEP.md` | 英文结构化指令（角色/任务/标准/流程）+ **强制简体中文应答**；与 Anthropic 等官方材料一致：先明确角色与任务，再列约束与输出流程 |
| 规划器 | `backend/app/modules/prompts/planning.py` | 英文 System：仅输出步骤级 JSON；步骤文案 **简体中文**；禁工具键 |
| 单步 ReAct | `backend/app/modules/prompts/step_react.py` | 英文 System：每轮单一 JSON；`final_answer` 面向用户为 **简体中文**；嵌入工具目录 |
| 执行后总结 | `backend/app/modules/prompts/assistant_reply.py` | 英文 System：综合计划与工具轨迹；默认 **简体中文** 作答 |
| Learner 反思 | `backend/app/modules/prompts/learner_reflection.py` | 英文 System：`reflection` / `rationale` 为 **简体中文**；仅 JSON |
| ReAct 首轮 / 收官 User | `backend/app/modules/execution/step_react_loop.py` | 首轮任务与「工具已成功请 final_answer」提示为英文，与用户中文内容同一上下文 |
| 规划解析重试 User | `backend/app/modules/planning/llm.py` | `_PLANNER_PARSE_RETRY_USER_HINT`：英文纠偏，与 Planner System 一致 |

### 1.2 存在的问题

- 所有提示词硬编码在 Python 文件中
- 无法运行时调整
- 无版本管理
- 无 A/B 测试能力
- 工具描述格式单一

---

## 二、优化方案

### 2.1 Tier 1: 提示词模板化（2-3 天）

**现状**：字符串直接拼接

```python
# 当前
FRAMEWORK_ROUTER_SYSTEM = """你是认知框架路由助手。根据用户当前任务... """
```

**方案**：使用模板引擎

```python
# backend/app/agent/prompts/templates.py

from string import Template
from dataclasses import dataclass
from typing import Callable

@dataclass
class PromptTemplate:
    name: str
    template: Template
    description: str
    version: str = "v1"

# ReAct 模板
REACT_TEMPLATE = PromptTemplate(
    name="react_system",
    version="v1",
    description="ReAct Agent System Prompt",
    template=Template("""你是 ReAct 智能体（Reason + Act）。

【对话模式】${conversation_mode}

【工具目录】
${tools_catalog}

${user_context}

${few_shot_examples}

【输出格式】
- 调用工具：{"thought":"简要推理","action":"工具名","action_input":${args_schema}}
- 直接回答：{"thought":"简要推理","final_answer":"完整回答"}
"""),
)

def render_react_prompt(
    tools_catalog: str,
    user_context: str = "",
    few_shot_examples: str = "",
    conversation_mode: str = "auto",
) -> str:
    return REACT_TEMPLATE.template.substitute(
        tools_catalog=tools_catalog,
        user_context=f"【上下文】\n{user_context}" if user_context else "",
        few_shot_examples=f"【示例】\n{few_shot_examples}" if few_shot_examples else "",
        conversation_mode=conversation_mode,
    )
```

---

### 2.2 Tier 1: 提示词版本管理（2-3 天）

**方案**：数据库存储 + 缓存

```sql
-- prompts 表
CREATE TABLE prompts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    variables JSONB,                    -- 模板变量定义
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, version)
);

CREATE TABLE prompt_audit (
    id SERIAL PRIMARY KEY,
    prompt_id INTEGER REFERENCES prompts(id),
    action VARCHAR(20),                 -- "create", "activate", "rollback"
    changed_at TIMESTAMP DEFAULT NOW(),
    changed_by VARCHAR(100)
);
```

```python
# backend/app/agent/prompts/registry.py

from functools import lru_cache

class PromptRegistry:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._cache: dict[str, str] = {}

    async def get(self, name: str, version: str | None = None) -> str:
        cache_key = f"{name}:{version or 'latest'}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        if version:
            row = await self._db.execute(
                select(prompts).where(
                    prompts.c.name == name,
                    prompts.c.version == version,
                    prompts.c.is_active == True
                )
            )
        else:
            row = await self._db.execute(
                select(prompts).where(
                    prompts.c.name == name,
                    prompts.c.is_active == True
                ).order_by(prompts.c.created_at.desc()).limit(1)
            )

        result = row.scalar_one_or_none()
        if not result:
            raise ValueError(f"Prompt not found: {name}:{version}")

        self._cache[cache_key] = result.content
        return result.content

    async def activate_version(self, name: str, version: str):
        """灰度/回滚"""
        # 1. 停用当前版本
        await self._db.execute(
            update(prompts).where(
                prompts.c.name == name,
                prompts.c.is_active == True
            ).values(is_active=False)
        )

        # 2. 激活新版本
        await self._db.execute(
            update(prompts).where(
                prompts.c.name == name,
                prompts.c.version == version
            ).values(is_active=True)
        )

        # 3. 清除缓存
        self._cache.clear()
```

**API 接口**：

```python
# backend/app/api/v1/prompts.py

@router.get("/{name}")
async def get_prompt(name: str, version: str | None = None):
    return {"content": await registry.get(name, version)}

@router.post("/{name}/versions")
async def create_version(name: str, data: PromptCreate):
    """创建新版本（不激活）"""
    prompt_id = await registry.create(name, data.version, data.content)

@router.post("/{name}/activate/{version}")
async def activate_version(name: str, version: str):
    """激活指定版本（用于灰度/回滚）"""
    await registry.activate_version(name, version)
```

---

### 2.3 Tier 2: 动态 System Prompt（3-5 天）

**方案**：运行时注入上下文

```python
# backend/app/agent/prompts/dynamic.py

def build_dynamic_system_prompt(
    base_name: str,
    context: dict[str, str],
) -> str:
    """构建动态 System Prompt"""

    # 1. 获取基础模板
    base = registry.get(base_name)

    # 2. 注入上下文变量
    substitutions = {}
    for key, value in context.items():
        substitutions[key] = value

    template = Template(base)
    return template.substitute(**substitutions)

# 使用示例
async def planner_node(state: AgentState):
    # 构建上下文
    context = {
        "user_context": await memory_manager.get_user_context(user_id),
        "session_summary": state.get("summary", ""),
        "blackboard_notes": "\n".join(state.get("blackboard_notes", [])),
    }

    # 渲染动态 Prompt
    system_prompt = build_dynamic_system_prompt("planner", context)

    # 调用 LLM
    messages = [SystemMessage(content=system_prompt), *chat_messages]
```

---

### 2.4 Tier 2: Few-shot 示例池（3-5 天）

**方案**：可配置的示例注入

```sql
-- examples 表
CREATE TABLE prompt_examples (
    id SERIAL PRIMARY KEY,
    prompt_name VARCHAR(100),          -- 关联的 prompt
    category VARCHAR(50),              -- 示例分类
    input_text TEXT NOT NULL,
    output_text TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
```

```python
# backend/app/agent/prompts/fewshot.py

class FewShotManager:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_examples(
        self,
        prompt_name: str,
        query: str,
        category: str | None = None,
        limit: int = 2,
    ) -> str:
        """获取最相关的示例"""

        # 简单关键词匹配（可升级为向量检索）
        rows = await self._db.execute(
            select(prompt_examples).where(
                prompt_examples.c.prompt_name == prompt_name,
                prompt_examples.c.is_active == True,
                *([prompt_examples.c.category == category] if category else [])
            ).limit(limit * 2)  # 多取一些再筛选
        )

        # 简单相似度计算
        query_words = set(query.lower().split())
        scored = []
        for row in rows:
            score = len(query_words & set(row.input_text.lower().split()))
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        if not top:
            return ""

        # 格式化为示例
        lines = ["【参考示例】"]
        for _, ex in top:
            lines.append(f"\n输入：{ex.input_text}")
            lines.append(f"输出：{ex.output_text}")

        return "\n".join(lines)
```

**在 ReAct Prompt 中使用**：

```python
async def react_node(state: AgentState):
    # 获取相关示例
    examples = await fewshot_manager.get_examples(
        prompt_name="react",
        query=state["user_message"],
        limit=2,
    )

    # 渲染 Prompt
    prompt = render_react_prompt(
        tools_catalog=tools_catalog,
        user_context=state.get("user_context", ""),
        few_shot_examples=examples,
    )
```

---

### 2.5 Tier 3: 提示词 A/B 测试（可选，5-7 天）

```python
# backend/app/agent/prompts/experiment.py

class PromptExperiment:
    """提示词实验管理器"""

    async def get_prompt_for_user(
        self,
        prompt_name: str,
        user_id: str,
    ) -> tuple[str, str]:
        """返回 (prompt_content, experiment_group)"""

        # 查询用户的实验分组（可以用 user_id hash）
        group = await self._get_user_group(user_id)

        if group == "B":
            return await registry.get(prompt_name, version="B"), "B"
        else:
            return await registry.get(prompt_name, version="A"), "A"

    async def record_outcome(
        self,
        user_id: str,
        prompt_name: str,
        success: bool,
        latency_ms: float,
    ):
        """记录实验结果"""
        await self._db.execute(
            insert(experiment_results).values(
                user_id=user_id,
                prompt_name=prompt_name,
                success=success,
                latency_ms=latency_ms,
            )
        )
```

---

## 三、实施优先级

| 优先级 | 优化项 | 工作量 | 效果 |
|--------|--------|--------|------|
| P0 | 模板引擎重构 | 2-3 天 | 代码可维护 |
| P0 | 数据库版本管理 | 2-3 天 | 可回滚可灰度 |
| P1 | 动态变量注入 | 3-5 天 | Prompt 随上下文 |
| P1 | Few-shot 示例池 | 3-5 天 | 质量提升 |
| P2 | A/B 测试框架 | 5-7 天 | 数据驱动优化 |

---

## 四、关键配置

```python
# config.py

class Settings:
    # 提示词版本
    active_prompt_version: str = "v1"

    # Few-shot
    enable_few_shot: bool = True
    few_shot_limit: int = 2

    # 实验
    enable_prompt_experiment: bool = False
    experiment_groups: list[str] = ["A", "B"]
```

---

## 五、示例：完整调用流程

```python
# backend/app/agent/nodes/planner_node.py

async def planner_node(state: AgentState):
    # 1. 获取基础 Prompt（支持版本管理）
    system_prompt = await prompt_registry.get("planner_system")

    # 2. 注入动态上下文
    context = {
        "user_context": await session_memory.get_context(state["session_id"]),
        "blackboard": "\n".join(state.get("blackboard_notes", [])),
        "summary": state.get("summary", ""),
    }

    # 3. 获取 Few-shot 示例
    examples = await fewshot_manager.get_examples(
        "planner", state["user_message"], limit=2
    )

    # 4. 渲染完整 Prompt
    prompt = build_planner_prompt(
        base=system_prompt,
        context=context,
        examples=examples,
    )

    # 5. 调用 LLM
    messages = [SystemMessage(content=prompt), *chat_messages]
    response = await ainvoke_with_retry(chat, messages)

    # 6. 记录实验（如果启用）
    if settings.enable_prompt_experiment:
        await experiment.record_outcome(
            user_id=state["session_id"],
            prompt_name="planner_system",
            success=True,
            latency_ms=elapsed,
        )
```

---

## 六、总结

| 层级 | 方案 | 收益 |
|------|------|------|
| **模板化** | 硬编码 → Template | 代码清晰易维护 |
| **版本管理** | 无 → 数据库 + 缓存 | 可灰度可回滚 |
| **动态注入** | 静态 → 上下文拼接 | Prompt 随状态变 |
| **Few-shot** | 无 → 示例池 | 特定任务质量提升 |
| **A/B 测试** | 无 → 实验框架 | 数据驱动优化 |
