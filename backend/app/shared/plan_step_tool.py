"""计划单步中 tool / 参数的宽松解析（规划校验与 Actor 执行共用）。"""

from __future__ import annotations

import json
from typing import Any

from app.shared.react_llm_output import (
    extract_react_action_field,
    is_pseudo_react_tool_name,
    pick_action_input,
)

def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value.strip())
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _name_from_tool_object(obj: dict[str, Any]) -> str | None:
    n = extract_react_action_field(obj)
    if n:
        return n
    for key in ("name", "tool_name", "function_name"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def extract_plan_step_tool(step: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """从规划步骤 dict 解析工具名与参数。

    兼容：根级 ``tool`` 字符串；``tool`` 为含 name 的对象；``tool_name`` / ``action`` 等别名；
    简易 OpenAI 式 ``function_call``；根级 ``function`` 对象；根级与嵌套中的 ``args`` / JSON 字符串。
    伪工具名（如 ``final_answer``、``none``）视为本步不调用注册表工具。
    """
    name: str | None = None
    args_nested: dict[str, Any] = {}

    raw_tool = step.get("tool")
    if isinstance(raw_tool, str) and raw_tool.strip():
        name = raw_tool.strip()
    elif isinstance(raw_tool, dict):
        name = _name_from_tool_object(raw_tool)
        args_nested = pick_action_input(raw_tool)
    elif isinstance(raw_tool, list) and raw_tool:
        first = raw_tool[0]
        if isinstance(first, str) and first.strip():
            name = first.strip()
        elif isinstance(first, dict):
            name = _name_from_tool_object(first)
            args_nested = pick_action_input(first)

    if not name:
        name = extract_react_action_field(step)

    if not name:
        fc = step.get("function_call")
        if isinstance(fc, dict):
            n = fc.get("name")
            if isinstance(n, str) and n.strip():
                name = n.strip()
            fc_args = _coerce_dict(fc.get("arguments"))
            if fc_args:
                args_nested = {**args_nested, **fc_args}

    if not name:
        fn = step.get("function")
        if isinstance(fn, dict):
            name = _name_from_tool_object(fn)
            if name:
                args_nested = {**pick_action_input(fn), **args_nested}

    if not name or is_pseudo_react_tool_name(name):
        return None, {}

    root_args = pick_action_input(step)
    merged: dict[str, Any] = {**args_nested, **root_args}
    return name, merged
