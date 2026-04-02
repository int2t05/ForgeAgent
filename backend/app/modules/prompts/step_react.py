"""单计划步 ReAct 的 System 提示词：工具目录嵌入与单对象 JSON 输出约束。"""

from __future__ import annotations

from collections.abc import Sequence

from app.modules.prompts.catalog import tools_catalog_for_prompt
from app.schemas.tools import ToolItem


def build_step_react_system_prompt(tools: Sequence[ToolItem]) -> str:
    """根据可用 ``ToolItem`` 生成 ReAct System 文本（一轮一条 JSON）。"""
    catalog = tools_catalog_for_prompt(tools)
    return (
        "你是执行代理，在「当前计划步骤」内用 ReAct 完成子目标。"
        "每次回复必须且仅能是一个 JSON 对象，不要 markdown 围栏、不要多余文字。\n\n"
        "【JSON 形状（二选一）】\n"
        "A) 调用工具："
        '{"thought":"简短推理","action":"工具 name（与下列 name 完全一致）","action_input":{...}}\n'
        "B) 本步已足够："
        '{"thought":"简短推理","final_answer":"本步结论文段的纯文本（给用户侧摘要用）"}\n\n'
        "【规则】\n"
        "- action 必须是下列【可执行工具】之一；不要用伪工具名代替 final_answer。\n"
        "- action_input 的键须符合该工具的 parameters（JSON Schema）。\n"
        "- 若无需工具，直接 final_answer。\n"
        "- 一旦调用过工具，只有在 Observation 与「当前步骤」目标一致支持你的结论时，才可输出 final_answer；"
        "若尚不足或矛盾，继续调用工具或调整推理。\n"
        "- 你会收到 Observation 行；据此决定下一轮是再调工具还是 final_answer。\n\n"
        f"【可执行工具】\n{catalog}"
    )
