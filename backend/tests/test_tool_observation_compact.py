"""tool_observation_compact：Observation 与轨迹摘要长度控制。"""

from __future__ import annotations

import json

from app.modules.memory.tool_observation_compact import (
    compact_json_for_prompt,
    observation_json_for_llm,
    shrink_tool_result_data,
)


def test_shrink_string() -> None:
    s = "x" * 5000
    out = shrink_tool_result_data(s, 200)
    assert isinstance(out, str)
    assert len(out) <= 250
    assert "已截断" in out


def test_shrink_dict_keeps_when_small() -> None:
    d = {"a": 1, "b": "hi"}
    assert shrink_tool_result_data(d, 500) == d


def test_shrink_dict_becomes_truncated_string_when_huge() -> None:
    d = {"text": "z" * 10000}
    out = shrink_tool_result_data(d, 300)
    assert isinstance(out, str)
    assert len(out) <= 400


def test_observation_caps_total_json() -> None:
    last = {"ok": True, "data": {"body": "n" * 50000}, "error": None}
    raw = observation_json_for_llm("read_file", last, max_json_chars=2000)
    assert len(raw) <= 2500
    obj = json.loads(raw)
    assert obj["tool"] == "read_file"
    assert obj["ok"] is True


def test_compact_json_for_prompt() -> None:
    blob = compact_json_for_prompt([{"x": "y" * 8000}], max_chars=500)
    assert len(blob) <= 600
