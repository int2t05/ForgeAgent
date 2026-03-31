"""规划器 JSON 抽取：覆盖「有时能解析有时不能」的典型模型输出（无需真实 LLM）。"""

from __future__ import annotations

import pytest

from app.modules.planning.llm import _extract_json_object, _normalize_steps

_VALID_STEPS = (
    '{"steps":[{"id":"1","title":"分析需求"},{"id":"2","title":"实现与验证"}]}'
)


class TestExtractJsonObject:
    """``_extract_json_object``：应用 JSONDecoder.raw_decode，避免贪心 ``{...}`` 误截断。"""

    def test_plain_object(self) -> None:
        data = _extract_json_object(_VALID_STEPS)
        assert data == {
            "steps": [
                {"id": "1", "title": "分析需求"},
                {"id": "2", "title": "实现与验证"},
            ],
        }

    def test_preamble_then_json(self) -> None:
        text = f"好的，计划如下：\n{_VALID_STEPS}"
        data = _extract_json_object(text)
        assert data is not None and "steps" in data

    def test_json_then_trailing_brace_comment_fails_with_greedy_regex_but_ok_now(self) -> None:
        """旧实现：``\\{{[\\s\\S]*\\}}`` 会吞到文末最后一个 ``}}``，常得到非法 JSON。"""
        text = (
            _VALID_STEPS
            + "\n\n备注：若 x 大于 0 请走 {分支A} 否则走 {{默认}}。\n"
            + "附加键值 demo：{\"k\":1}"
        )
        data = _extract_json_object(text)
        assert data is not None
        assert len(data.get("steps", [])) == 2

    def test_markdown_fence(self) -> None:
        text = "```json\n" + _VALID_STEPS + "\n```"
        data = _extract_json_object(text)
        assert data is not None and data["steps"][0]["title"] == "分析需求"

    def test_root_array_not_accepted_as_dict(self) -> None:
        text = '[{"id":"1","title":"only"}]'
        assert _extract_json_object(text) is None

    def test_invalid_no_recoverable_object(self) -> None:
        assert _extract_json_object("全是自然语言没有大括号") is None


class TestNormalizeSteps:
    def test_valid(self) -> None:
        data = _extract_json_object(_VALID_STEPS)
        assert data is not None
        steps = _normalize_steps(data)
        assert steps is not None
        assert len(steps) == 2
        assert steps[0]["title"] == "分析需求"

    def test_single_step_ok(self) -> None:
        one = '{"steps":[{"id":"1","title":"一步"}]}'
        data = _extract_json_object(one)
        assert data is not None
        steps = _normalize_steps(data)
        assert steps is not None
        assert len(steps) == 1
        assert steps[0]["title"] == "一步"

    def test_empty_steps_rejected(self) -> None:
        data = _extract_json_object('{"steps":[]}')
        assert data is not None
        assert _normalize_steps(data) is None

    def test_optional_tool_and_args(self) -> None:
        raw = (
            '{"steps":['
            '{"id":"1","title":"复述","tool":"echo","args":{"text":"你好"}},'
            '{"id":"2","title":"检索","tool":"mock_search","args":{"query":"x"}}'
            "]}"
        )
        data = _extract_json_object(raw)
        assert data is not None
        steps = _normalize_steps(data)
        assert steps is not None
        assert steps[0].get("tool") == "echo"
        assert steps[0].get("args") == {"text": "你好"}
        assert steps[1].get("tool") == "mock_search"
        assert steps[1].get("args") == {"query": "x"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
