"""注入 LLM 的 Observation / 轨迹片段压缩：大工具返回只保留前缀 + 截断提示（完整结果仍在事件流）。

与 ``llm_context_budget``、``conversation_summary`` 同属记忆域的上下文整形；由 ReAct 等执行路径调用。
"""

from __future__ import annotations

import json
from typing import Any

_TAIL = "\n[... 已截断；完整 tool_result 见任务时间线 ...]"


def shrink_tool_result_data(data: Any, max_chars: int) -> Any:
    """将 ``data`` 压到约 ``max_chars`` 字符内；超长时用可读的截断字符串，避免 Observation JSON 撑爆上下文。"""
    if data is None or max_chars < 32:
        return data
    if isinstance(data, str):
        if len(data) <= max_chars:
            return data
        return data[: max(0, max_chars - len(_TAIL))] + _TAIL
    try:
        ser = json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        ser = str(data)
    if len(ser) <= max_chars:
        return data
    return ser[: max(0, max_chars - len(_TAIL))] + _TAIL


def compact_json_for_prompt(obj: Any, max_chars: int) -> str:
    """将任意可序列化对象压成 JSON 字符串，供首轮 HumanMessage 等使用。"""
    cap = max(64, int(max_chars))
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(obj)
    if len(s) <= cap:
        return s
    return s[: max(0, cap - len(_TAIL))] + _TAIL


def observation_json_for_llm(
    tool_name: str,
    last_exec: dict[str, Any],
    *,
    max_json_chars: int,
) -> str:
    """生成写入 observation HumanMessage 的 JSON 字符串（总长度上限 ``max_json_chars``）。"""
    cap = max(256, int(max_json_chars))
    err = last_exec.get("error")
    if isinstance(err, str) and len(err) > 2000:
        err = err[: 2000 - len(_TAIL)] + _TAIL

    overhead = len(tool_name) + 120
    data_budget = max(128, cap - overhead - (len(err) if isinstance(err, str) else 0))
    data_compact = shrink_tool_result_data(last_exec.get("data"), data_budget)

    payload: dict[str, Any] = {
        "tool": tool_name,
        "ok": last_exec.get("ok"),
        "error": err,
        "data": data_compact,
    }
    out = json.dumps(payload, ensure_ascii=False)
    if len(out) <= cap:
        return out

    payload["data"] = shrink_tool_result_data(data_compact, max(128, cap // 2))
    out = json.dumps(payload, ensure_ascii=False)
    if len(out) <= cap:
        return out
    payload["data"] = "[大型返回已省略；完整 tool_result 见任务时间线]"
    payload["data_omitted"] = True
    return json.dumps(payload, ensure_ascii=False)
