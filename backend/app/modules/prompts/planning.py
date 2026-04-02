"""规划阶段 System 提示（步骤 JSON 与工具目录）。"""

from __future__ import annotations

from collections.abc import Sequence

from app.modules.prompts.catalog import tools_catalog_for_prompt
from app.schemas.tools import ToolItem


def build_planner_system_prompt(tools: Sequence[ToolItem]) -> str:
    """生成规划阶段使用的 System 提示串（JSON 步骤契约与动态工具目录）。"""
    catalog_block = tools_catalog_for_prompt(tools)
    if tools:
        names_line = "、".join(t.name for t in tools)
        tool_rules = (
            '若某步需要调用工具：字段 "tool" 必须是【已注册工具】中某一个 "name"（精确匹配，区分大小写）；'
            '"args" 为 JSON 对象，键与取值须符合该工具的 "parameters"（JSON Schema），勿臆造字段名。'
        )
    else:
        names_line = "（当前无已注册工具）"
        tool_rules = '当前无可用工具：所有步骤均不得包含 "tool" 与 "args"。'

    return (
        "你是任务规划助手。根据用户与助手的前文对话及当前诉求，只输出一个 JSON 对象，"
        "不要 markdown 代码块、不要代码围栏、不要额外说明文字。\n\n"
        "【输出 JSON 形状】\n"
        '{"steps":[{"id":"步骤编号字符串","title":"步骤简述（简短中文）",'
        '"tool":"可选；仅当本步要调用工具时填写","args":{}}]}\n'
        "说明：分析与纯推理步骤可省略 \"tool\" 与 \"args\"；需要工具时必须同时给出二者。\n\n"
        "【步骤与工具约束】\n"
        f"- 至少 1 个步骤。\n"
        f"- {tool_rules}\n"
        f"- 当前允许的 tool 名称：{names_line}\n\n"
        "【已注册工具】（name、description、parameters 为入参 JSON Schema，可能为空）\n"
        f"{catalog_block}"
    )
