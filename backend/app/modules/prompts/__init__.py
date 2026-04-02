"""LLM 提示词与注入工具目录文本（按域分子模块，统一管理）。

模块组织：
  - **planning.py**：Planner / Skill Selector system prompt
  - **step_react.py**：单步 ReAct system prompt
  - **assistant_reply.py**：执行后流式总结 system prompt
  - **learner_reflection.py**：Learner 反思 system prompt + user payload 构建
  - **react_hints.py**：ReAct 循环辅助提示词（收口轮 nudge、技能导入前缀）
  - **parse_retry.py**：JSON 解析重试提示词（各 LLM 调用点统一使用）
  - **catalog.py**：工具目录文本生成

设计原则：
  1. 所有 system prompt 集中在此包，避免散落在业务逻辑文件中
  2. 解析重试 hint 统一管理，便于维护和国际化
  3. 按功能域分模块，与四模块架构对齐

使用方式：
  from app.modules.prompts.planning import build_planner_system_prompt
  from app.modules.prompts.step_react import build_step_react_system_prompt
  from app.modules.prompts.parse_retry import REACT_PARSE_RETRY, PLANNER_PARSE_RETRY
"""

from app.modules.prompts.assistant_reply import ASSISTANT_EXECUTOR_SUMMARY_SYSTEM
from app.modules.prompts.catalog import tools_catalog_for_prompt
from app.modules.prompts.planning import (
    build_planner_system_prompt,
    build_skill_selector_system_prompt,
)
from app.modules.prompts.step_react import build_step_react_system_prompt

__all__ = [
    "ASSISTANT_EXECUTOR_SUMMARY_SYSTEM",
    "build_planner_system_prompt",
    "build_skill_selector_system_prompt",
    "build_step_react_system_prompt",
    "tools_catalog_for_prompt",
]
