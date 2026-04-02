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
        "【JSON 形状】\n"
        "1) 只输出终答："
        '{"thought":"…","final_answer":"本步结论（给用户侧摘要）"}\n'
        "2) 单工具："
        '{"thought":"…","action":"name","action_input":{...}}\n'
        "3) 同一轮多工具（按数组顺序执行，完成后你会依次收到多条 Observation）："
        '{"thought":"…","actions":[{"action":"name1","action_input":{...}},{"action":"name2","action_input":{...}}]}\n\n'
        "【规则】\n"
        "- 同一 JSON 中若含 actions（或非空的 tool_calls/calls）则只走工具路径，不要同时写 final_answer；"
        "读回 Observation 后再在下一轮决定继续 tools 或 final_answer。\n"
        "- action / actions[].action 须与下列【可执行工具】 name 完全一致；不要用伪工具名代替终答。\n"
        "- action_input 须符合各工具的 parameters（JSON Schema）。\n"
        "- 无需工具时只用 final_answer。\n"
        "- 你会收到 Observation；根据事实与步骤目标决定下一轮。\n"
        "- 当 Observation 表明工具已成功（ok=true）且子目标已达成时，下一轮应输出 final_answer 收束本步，"
        "避免继续重复调用相同工具或无谓占用轮次。\n\n"
        f"【可执行工具】\n{catalog}"
    )
