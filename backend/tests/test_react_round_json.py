"""ReAct 轮次 JSON：须含 action 或 final_answer，避免误取文档示例。"""

from app.shared.react_llm_output import (
    _FINAL_ANSWER_TRUE,
    coerce_final_answer_value,
    extract_tool_invocations,
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


def test_actions_batch_order():
    raw = (
        '{"thought":"t","actions":['
        '{"action":"read_file","action_input":{"file_path":"a"}},'
        '{"tool":"list_directory","args":{"dir_path":"b"}}'
        "]}"
    )
    d = parse_react_round_json(raw)
    assert d is not None
    inv = extract_tool_invocations(d)
    assert inv == [
        ("read_file", {"file_path": "a"}),
        ("list_directory", {"dir_path": "b"}),
    ]


# 新增：测试 final_answer boolean 语义


def test_final_answer_boolean_true_returns_sentinel():
    """final_answer: true (boolean) 应返回哨兵值表示子目标满足。"""
    raw = '{"thought":"t","final_answer":true}'
    d = parse_react_round_json(raw)
    assert d is not None
    fa = pick_final_answer(d)
    assert fa == _FINAL_ANSWER_TRUE


def test_coerce_final_answer_true_string_converts_to_sentinel():
    """字符串 "true" 应被转换为哨兵值（兼容模型输出）。"""
    assert coerce_final_answer_value("true") == _FINAL_ANSWER_TRUE
    assert coerce_final_answer_value("True") == _FINAL_ANSWER_TRUE
    assert coerce_final_answer_value("TRUE") == _FINAL_ANSWER_TRUE


def test_coerce_final_answer_boolean_true_returns_sentinel():
    """布尔值 true 应返回哨兵值。"""
    assert coerce_final_answer_value(True) == _FINAL_ANSWER_TRUE


def test_final_answer_false_or_none_returns_none():
    """false 或 None 不应返回有效终答；布尔 False 转为字符串 'False' 视为有效内容。"""
    assert coerce_final_answer_value(None) is None
    assert coerce_final_answer_value("") is None
    # 布尔 False 通过 int/float 分支转为字符串 "False"，视为有效内容
    assert coerce_final_answer_value(False) == "False"
    # 字符串 "false" 仍视为有效内容
    assert coerce_final_answer_value("false") == "false"


def test_final_answer_legacy_string_still_works():
    """旧格式的字符串 final_answer 仍可正常解析（向后兼容）。"""
    raw = '{"thought":"t","final_answer":"已完成"}'
    d = parse_react_round_json(raw)
    assert d is not None
    fa = pick_final_answer(d)
    assert fa == "已完成"

