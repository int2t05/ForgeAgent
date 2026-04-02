"""从大模型单轮输出中提取 ReAct 形态字段（与规划域 JSON 候选解析协作）。

纯函数、无 DB；供执行域 ReAct 与其它需对齐契约的调用方复用。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.shared.llm_json_parse import collect_json_candidates, try_parse_single_candidate

# 模型把「应输出 final_answer」误写成 action 时的常用占位名（小写 + 下划线规范化后匹配）
_PSEUDO_REACT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "final_answer",
        "finalanswer",
        "answer",
        "respond",
        "response",
        "reply",
        "done",
        "complete",
        "completed",
        "finished",
        "finish",
        "end_turn",
        "endturn",
        "terminate",
        "none",
        "null",
        "no_tool",
        "no_tool_call",
        "direct",
        "user_reply",
        "submit",
        "final",
        "give_answer",
        "return_answer",
    }
)

_ANSWER_FIELD_KEYS: tuple[str, ...] = (
    "final_answer",
    "answer",
    "response",
    "reply",
    "output",
    "content",
    "text",
    "message",
    "echoed",
)

_ACTION_FIELD_KEYS: tuple[str, ...] = (
    "action",
    "tool",
    "tool_name",
    "function_name",
    "function",
)

_THOUGHT_FIELD_KEYS: tuple[str, ...] = (
    "thought",
    "reasoning",
    "thinking",
    "think",
    "analysis",
    "rationale",
    "reflection",
    "反思",
    "redacted_thinking",
    "redacted_reasoning",
)

_ACTION_INPUT_KEYS: tuple[str, ...] = (
    "action_input",
    "tool_input",
    "arguments",
    "args",
    "parameters",
    "params",
)


def _normalize_pseudo_name(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    return s


def is_pseudo_react_tool_name(name: str) -> bool:
    """是否为「伪工具名」（本应走 final_answer 语义，不得当注册表工具调用）。"""
    if not name or not str(name).strip():
        return False
    n = _normalize_pseudo_name(str(name))
    return n in _PSEUDO_REACT_TOOL_NAMES


def coerce_final_answer_value(value: Any) -> str | None:
    """将任意类型规整为非空终答字符串；无法表示则 None。"""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (dict, list)):
        try:
            s = json.dumps(value, ensure_ascii=False).strip()
            return s if s else None
        except (TypeError, ValueError):
            return None
    s = str(value).strip()
    return s if s else None


def extract_react_action_field(data: dict[str, Any]) -> str | None:
    """取出模型声明的 action/tool 等字段原始字符串（不做伪工具过滤）。"""
    for key in _ACTION_FIELD_KEYS:
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def pick_action_input(data: dict[str, Any]) -> dict[str, Any]:
    """解析工具入参，兼容 action_input、arguments、input 等别名。"""
    for key in _ACTION_INPUT_KEYS:
        v = data.get(key)
        if isinstance(v, dict):
            return dict(v)
        if isinstance(v, str) and v.strip():
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return dict(parsed)
    inp = data.get("input")
    if isinstance(inp, dict):
        return dict(inp)
    if isinstance(inp, str) and inp.strip():
        try:
            parsed = json.loads(inp)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, dict):
                return dict(parsed)
    return {}


def pick_final_answer(data: dict[str, Any]) -> str | None:
    """终答：根级别名 + 将 action=伪工具 且正文在 action_input 内的情况合并进来。"""
    for key in _ANSWER_FIELD_KEYS:
        s = coerce_final_answer_value(data.get(key))
        if s:
            return s
    raw_action = extract_react_action_field(data)
    if raw_action and is_pseudo_react_tool_name(raw_action):
        inp = pick_action_input(data)
        for key in _ANSWER_FIELD_KEYS:
            s = coerce_final_answer_value(inp.get(key))
            if s:
                return s
        if len(inp) == 1:
            s = coerce_final_answer_value(next(iter(inp.values())))
            if s:
                return s
    return None


def pick_react_tool_name(data: dict[str, Any]) -> str | None:
    """可交给注册表调用的真实工具名；伪工具名（如 final_answer）返回 None。"""
    act = extract_react_action_field(data)
    if not act or is_pseudo_react_tool_name(act):
        return None
    return act


def pick_thought(data: dict[str, Any]) -> str | None:
    """单轮推理文本（多别名）。"""
    for key in _THOUGHT_FIELD_KEYS:
        v = data.get(key)
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
    return None


def react_payload_has_action_or_answer(data: dict[str, Any]) -> bool:
    """是否含可提交的终答或可调用工具名（避免把文档示例 JSON 当成本轮输出）。"""
    return bool(pick_final_answer(data) or pick_react_tool_name(data))


def parse_react_round_json(text: str) -> dict[str, Any] | None:
    """在多段候选中取首个同时含终答或可执行工具名的对象。"""
    if not text or not str(text).strip():
        return None
    for cand in collect_json_candidates(text):
        d = try_parse_single_candidate(cand)
        if d and react_payload_has_action_or_answer(d):
            return d
    return None
