"""JSON 解析重试提示词：各 LLM 调用点在输出不符合 schema 时的用户消息补充。

统一管理所有 parse-retry hint，避免散落在业务逻辑文件中。
"""

# --- ReAct 循环 ---
REACT_PARSE_RETRY = (
    "Your last reply could not be parsed as required ReAct JSON. "
    "Reply with exactly one JSON object containing either "
    "`final_answer` or executable `action`/`actions` fields. "
    "Do not output markdown fences or extra text."
)

# --- Planner ---
PLANNER_PARSE_RETRY = (
    "Your last reply could not be parsed as the required JSON "
    "(root object must contain a non-empty `steps` array; each step must have a non-empty "
    "`title`; optional per-step `skill_imports` string array must follow the catalog). "
    "Reply with **only** one raw JSON object—no markdown fences, no other text."
)

# --- Skill Selector ---
SKILL_SELECTOR_PARSE_RETRY = (
    "Your last reply could not be parsed as the required JSON "
    "(root object must contain a non-empty `skill_imports` array; values must be strings "
    "from the catalog). Reply with **only** one raw JSON object—no markdown fences, no other text."
)

# --- Learner ---
LEARNER_PARSE_RETRY = (
    "上一条助手回复无法解析为符合要求的 JSON（根对象须含非空字符串 reflection、"
    "布尔 request_replan、字符串 rationale）。"
    "请严格只输出一个 JSON 对象，不要 markdown 围栏、不要任何其他说明文字。"
)
