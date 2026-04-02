"""python_repl：兼容模型传入 ``code``（LangChain 底层只认 ``query``）。"""

import pytest

from app.modules.tools.builtin_executor import execute_builtin


@pytest.mark.asyncio
async def test_python_repl_accepts_code_param() -> None:
    from app.core.config import get_settings

    if not get_settings().agent_enable_python_repl:
        pytest.skip("python_repl disabled")
    r = await execute_builtin(
        "python_repl",
        {"code": "x = 40 + 2\nprint(x)"},
    )
    assert r["ok"] is True
    assert "42" in str(r["data"])


@pytest.mark.asyncio
async def test_python_repl_accepts_query_param() -> None:
    from app.core.config import get_settings

    if not get_settings().agent_enable_python_repl:
        pytest.skip("python_repl disabled")
    r = await execute_builtin(
        "python_repl",
        {"query": "print('q')"},
    )
    assert r["ok"] is True
    assert "q" in str(r["data"])
