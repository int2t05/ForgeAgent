"""LLM 提示词与注入工具目录文本（按域分子模块）。

- catalog：工具列表 JSON 块
- planning / react / framework_router / assistant_reply：各节点 System 或纠错文案
"""

from app.modules.prompts.assistant_reply import ASSISTANT_EXECUTOR_SUMMARY_SYSTEM
from app.modules.prompts.catalog import tools_catalog_for_prompt
from app.modules.prompts.framework_router import FRAMEWORK_ROUTER_SYSTEM
from app.modules.prompts.planning import build_planner_system_prompt
from app.modules.prompts.react import (
    REACT_JSON_PARSE_NUDGE,
    REACT_SHAPE_NUDGE,
    TOOL_FAILURE_NUDGE,
    build_react_system_prompt,
)

__all__ = [
    "ASSISTANT_EXECUTOR_SUMMARY_SYSTEM",
    "FRAMEWORK_ROUTER_SYSTEM",
    "REACT_JSON_PARSE_NUDGE",
    "REACT_SHAPE_NUDGE",
    "TOOL_FAILURE_NUDGE",
    "build_planner_system_prompt",
    "build_react_system_prompt",
    "tools_catalog_for_prompt",
]
