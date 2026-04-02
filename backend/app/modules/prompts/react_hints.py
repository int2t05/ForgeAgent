"""ReAct 循环辅助提示词：收口轮 nudge、解析重试 hint、技能导入前缀。

供 ``execution/step_react_loop`` 与 ``execution/step_react_internals`` 使用。
"""

CLOSING_FINAL_NUDGE = (
    "System: In this step every tool run succeeded (see Observations above).\n"
    "Reply with **only** one JSON object and **do not** include action, actions, tool_calls, or calls.\n"
    'Include final_answer as boolean true, e.g. {"thought":"one line","final_answer":true}'
)

_REACT_PARSE_RETRY_USER_HINT = (
    "Your last reply could not be parsed as required ReAct JSON. "
    "Reply with exactly one JSON object containing either "
    "`final_answer` or executable `action`/`actions` fields. "
    "Do not output markdown fences or extra text."
)

_SKILL_IMPORT_HUMAN_PREFIX = (
    "## Imported skill context (planner-selected, this step only)\n\n"
    "Content read from SKILL.md under the chosen directories. "
    "This is not the tool catalogue.\n\n"
)
