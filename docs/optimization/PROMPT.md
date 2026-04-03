# 提示词优化

## 提示词分布

| 节点 | 文件 | 内容 |
|------|------|------|
| 规划器 | `planning.py` | 英文 System，仅输出步骤级 JSON |
| ReAct | `step_react.py` | 英文 System，每轮单一 JSON |
| 总结 | `assistant_reply.py` | 英文 System，默认简体中文应答 |
| Learner | `learner_reflection.py` | 英文 System，reflection 简体中文 |

## 优化方案

### Tier 1: 模板化

```python
from string import Template

REACT_TEMPLATE = Template("""
你是 ReAct 智能体（Reason + Act）。

【工具目录】
${tools_catalog}

${user_context}
""")

def render_prompt(tools_catalog, user_context):
    return REACT_TEMPLATE.substitute(
        tools_catalog=tools_catalog,
        user_context=user_context
    )
```

### Tier 2: 版本管理

```sql
CREATE TABLE prompts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    version VARCHAR(20),
    content TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
```

### Tier 3: 动态注入

```python
def build_dynamic_prompt(base_name, context):
    base = registry.get(base_name)
    template = Template(base)
    return template.substitute(**context)
```

## 实施优先级

| 优先级 | 优化项 | 工作量 |
|--------|--------|--------|
| P0 | 模板引擎重构 | 2-3 天 |
| P0 | 数据库版本管理 | 2-3 天 |
| P1 | 动态变量注入 | 3-5 天 |
| P1 | Few-shot 示例池 | 3-5 天 |
| P2 | A/B 测试框架 | 5-7 天 |
