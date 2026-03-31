"""ToolRegistry.execute：内置工具与未知名称。"""

from __future__ import annotations

import pytest

from app.modules.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_execute_echo() -> None:
    reg = ToolRegistry()
    out = await reg.execute("echo", {"text": "hello"})
    assert out.get("ok") is True
    assert out.get("data") == {"echoed": "hello"}


@pytest.mark.asyncio
async def test_execute_mock_search() -> None:
    reg = ToolRegistry()
    out = await reg.execute("mock_search", {"query": "q"})
    assert out.get("ok") is True
    data = out.get("data")
    assert isinstance(data, dict)
    assert data.get("query") == "q"
    assert isinstance(data.get("results"), list)


@pytest.mark.asyncio
async def test_execute_unknown_tool() -> None:
    reg = ToolRegistry()
    out = await reg.execute("missing_tool_xyz", {})
    assert out.get("ok") is False
    assert "未知工具" in str(out.get("error", ""))
