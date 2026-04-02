"""``extract_plan_step_tool`` 别名与嵌套结构兼容。"""

from __future__ import annotations

from app.shared.plan_step_tool import extract_plan_step_tool


def test_tool_string():
    n, a = extract_plan_step_tool(
        {"id": "1", "title": "x", "tool": "list_tools", "args": {}}
    )
    assert n == "list_tools"
    assert a == {}


def test_tool_object_with_name():
    n, a = extract_plan_step_tool(
        {
            "id": "1",
            "title": "列目录",
            "tool": {"name": "list_dir", "args": {"path": "."}},
        }
    )
    assert n == "list_dir"
    assert a.get("path") == "."


def test_tool_name_alias():
    n, a = extract_plan_step_tool(
        {"id": "1", "title": "搜", "tool_name": "duckduckgo_search", "args": {"query": "q"}}
    )
    assert n == "duckduckgo_search"
    assert a["query"] == "q"


def test_function_call_openai_shape():
    n, a = extract_plan_step_tool(
        {
            "id": "1",
            "title": "调用",
            "function_call": {"name": "list_tools", "arguments": "{}"},
        }
    )
    assert n == "list_tools"
    assert a == {}


def test_pseudo_tool_is_no_tool():
    n, a = extract_plan_step_tool({"id": "1", "title": "想", "tool": "none"})
    assert n is None
    assert a == {}


def test_root_function_object():
    n, a = extract_plan_step_tool(
        {
            "id": "1",
            "title": "执行",
            "function": {"name": "list_tools", "parameters": {}},
        }
    )
    assert n == "list_tools"
