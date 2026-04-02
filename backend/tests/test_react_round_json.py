"""ReAct 轮次 JSON：须含 action 或 final_answer，避免误取文档示例。"""

from app.shared.react_llm_output import (
    parse_react_round_json,
    pick_final_answer,
    pick_react_tool_name,
)


def test_skips_example_json_in_markdown_prefers_real_react():
    text = '''# 文档

```json
{"status": "ok"}
```

正文。

```json
{"thought":"t","final_answer":"给用户的内容"}
```
'''
    d = parse_react_round_json(text)
    assert d == {"thought": "t", "final_answer": "给用户的内容"}


def test_noise_only_returns_none():
    text = '{"status": "ok"}'
    assert parse_react_round_json(text) is None


def test_single_valid_round():
    assert parse_react_round_json(
        '{"thought":"a","action":"read_file","action_input":{"file_path":"x"}}'
    ) == {
        "thought": "a",
        "action": "read_file",
        "action_input": {"file_path": "x"},
    }


def test_action_final_answer_treated_as_answer_not_tool():
    """模型将终答误写为 action=final_answer 时，不得当作注册表工具名。"""
    raw = '{"thought":"t","action":"final_answer","final_answer":"用户可见"}'
    d = parse_react_round_json(raw)
    assert d is not None
    assert pick_react_tool_name(d) is None
    assert pick_final_answer(d) == "用户可见"


def test_action_final_answer_body_in_action_input():
    raw = '{"thought":"t","action":"final_answer","action_input":{"text":"在 input 里"}}'
    d = parse_react_round_json(raw)
    assert d is not None
    assert pick_react_tool_name(d) is None
    assert pick_final_answer(d) == "在 input 里"


def test_pseudo_action_spaced_name():
    d = parse_react_round_json('{"action":"Final Answer","message":"m"}')
    assert pick_react_tool_name(d) is None
    assert pick_final_answer(d) == "m"
