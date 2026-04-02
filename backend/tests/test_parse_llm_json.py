"""``app.shared.llm_json_parse.parse_llm_json_object`` 回归用例。"""

from app.shared.llm_json_parse import parse_llm_json_object


def test_plain_object():
    assert parse_llm_json_object(
        '{"thought":"t","action":"echo","action_input":{}}'
    ) == {"thought": "t", "action": "echo", "action_input": {}}


def test_preamble_and_markdown_fence():
    raw = (
        '好的，我来处理。\n\n```json\n'
        '{"thought":"x","final_answer":"答"}\n'
        "```"
    )
    out = parse_llm_json_object(raw)
    assert out == {"thought": "x", "final_answer": "答"}


def test_inline_fence():
    out = parse_llm_json_object('说明\n```\n{"a":1}\n```\n尾')
    assert out == {"a": 1}


def test_extracts_embedded_json_object():
    """前文/后文夹杂时仍能抽出唯一根对象。"""
    bad = '说明文字，请看 {"thought":"t","final_answer":"ok"} 结束'
    assert parse_llm_json_object(bad) == {"thought": "t", "final_answer": "ok"}


def test_plain_text_no_object():
    assert parse_llm_json_object("只是普通说明，没有大括号") is None


def test_trailing_comma():
    assert parse_llm_json_object('{"thought":"a","action":"x","action_input":{},}') == {
        "thought": "a",
        "action": "x",
        "action_input": {},
    }


def test_smart_quotes():
    raw = """{\u201cthought\u201d: \u201cx\u201d, \u201cfinal_answer\u201d: \u201cy\u201d}"""
    assert parse_llm_json_object(raw) == {"thought": "x", "final_answer": "y"}


def test_python_single_quoted_dict_in_fence():
    raw = "```\n{'thought': 't', 'final_answer': 'ok'}\n```"
    assert parse_llm_json_object(raw) == {
        "thought": "t",
        "final_answer": "ok",
    }


def test_second_fence_when_first_invalid():
    raw = (
        "```json\nnot json at all\n```\n\n"
        '```\n{"action":"read_file","thought":"","action_input":{"file_path":"a.txt"}}\n```'
    )
    out = parse_llm_json_object(raw)
    assert out is not None
    assert out.get("action") == "read_file"
