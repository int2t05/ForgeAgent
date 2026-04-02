"""ReAct 路径：系统提示与轮次纠错 Human 注入文案。"""

from __future__ import annotations

REACT_SHAPE_NUDGE = (
    "系统提示：你上一段输出不符合约定。请只输出一个 JSON 对象（不要 markdown 围栏），"
    "且在以下两种形态中【严格二选一】：\n"
    '1) 还要调工具：{"thought":"…","action":"工具name","action_input":{…}}\n'
    '2) 已可答用户：{"thought":"…","final_answer":"…"}\n'
    "注意：final_answer / action 至少其一为非空；勿用空字符串凑字段；"
    "若可作答请直接给出 final_answer。"
)

TOOL_FAILURE_NUDGE = (
    "系统提示：上一工具调用失败（见上一条 Observation 中的 error）。"
    "请修正 action_input 后重试、改用其他 action，或输出 final_answer 向用户说明原因。"
)

REACT_JSON_PARSE_NUDGE = (
    "系统提示：你上一段输出无法解析为单个 JSON 对象（可能含多余说明、markdown 围栏或未转义换行）。"
    '请只输出一行或一段裸 JSON，形态二选一：{"thought":"…","action":"工具name","action_input":{…}} '
    '或 {"thought":"…","final_answer":"…"}；勿使用 ``` 代码块包裹。'
)


def build_react_system_prompt(catalog_block: str) -> str:
    """拼装 ReAct 轮次的系统提示（JSON 输出契约与工具目录块）。"""
    return (
        "你是 ReAct 智能体（Reason + Act）：每一步只输出一个 JSON 对象，不要 markdown、不要注释。\n\n"
        "【两种合法输出】恰含其一：\n"
        '1) 需调用工具：{"thought":"简要中文推理","action":"工具 name","action_input":{...}}\n'
        '2) 可回答用户：{"thought":"简要中文推理","final_answer":"给用户的完整中文答复"}\n\n'
        "action 必须是【工具目录】中某一工具的 name（区分大小写）；不得填 final_answer、answer、done 等占位词（应改用顶层 final_answer 字段）；"
        "action_input 的键须符合该工具的 parameters（JSON Schema）。\n"
        "（等价别名：thought 可用 reasoning/thinking 等；final_answer 可用 answer、text、message；"
        "action 可用 tool；action_input 可用 args。）\n"
        "禁止输出 ``` 代码围栏、禁止在 JSON 外再写大段说明；更不要把文档中的示例 JSON 当作你的回答。"
        "若需向用户展示文件全文，把全文放进 final_answer 字符串字段，不要单独贴 markdown 段落。\n\n"
        "【工具目录】\n"
        f"{catalog_block}"
    )
