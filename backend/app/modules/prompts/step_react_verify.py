"""单步 ReAct 终答核准：辅助模型仅输出 aligned / brief_reason JSON。"""

from __future__ import annotations

import json
from typing import Any


STEP_REACT_FINAL_ANSWER_VERIFY_SYSTEM = """你是审核员。根据用户任务、当前计划步骤、工具执行结果与模型给出的候选 final_answer，
判断候选结论是否与工具观测中的事实一致，且足以完成该步骤目标。
若存在失败调用（ok 为 false）却声称已成功达成目标，或结论与 data/error 矛盾，aligned 必须为 false。
仅输出一个 JSON 对象，不要 markdown 围栏、不要多余文字。

【输出形状】
{"aligned": true/false, "brief_reason": "简短中文理由"}"""


def build_step_react_final_answer_verify_user_content(
    *,
    user_message: str,
    step: dict[str, Any],
    call_results: list[dict[str, Any]],
    proposed_final: str,
) -> str:
    """组装审核用 User 侧结构化输入（单段 JSON 文本）。"""
    summary = [
        {
            "tool": c.get("tool"),
            "ok": c.get("ok"),
            "data": c.get("data"),
            "error": c.get("error"),
        }
        for c in call_results
    ]
    return json.dumps(
        {
            "用户任务": user_message,
            "当前步骤": step,
            "工具调用结果": summary,
            "候选final_answer": proposed_final,
        },
        ensure_ascii=False,
    )
