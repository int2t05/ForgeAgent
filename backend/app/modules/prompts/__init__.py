"""LLM 提示词与注入工具目录文本（按域分子模块）。

- catalog：工具列表 JSON 块
- planning：Planner / Skill Selector system prompt
- step_react：单步 ReAct system prompt
- assistant_reply：执行后流式总结 system prompt
"""

from app.modules.prompts.assistant_reply import ASSISTANT_EXECUTOR_SUMMARY_SYSTEM
from app.modules.prompts.catalog import tools_catalog_for_prompt
from app.modules.prompts.planning import build_planner_system_prompt

__all__ = [
    "ASSISTANT_EXECUTOR_SUMMARY_SYSTEM",
    "build_planner_system_prompt",
    "tools_catalog_for_prompt",
]
