"""内置工具回归：注册表列举与官方社区工具调用路径（网络依赖已打桩）。"""

import pytest

from app.modules.tools.builtin_executor import execute_builtin


async def _refresh_registry_without_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    """覆盖工作区 .env 中的 Tavily 密钥为空并重建快照，使测试与是否配置 Tavily 无关。"""
    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal
    from app.modules.tools.registry import tool_registry

    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    async with AsyncSessionLocal() as db:
        await tool_registry.refresh(db)
        await db.commit()


@pytest.mark.asyncio
async def test_list_tools_all_includes_search_tools_no_tavily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _refresh_registry_without_tavily(monkeypatch)
    r = await execute_builtin("list_tools", {})
    assert r["ok"] is True
    names = {t["name"] for t in r["data"]["tools"]}
    assert "list_tools" in names
    assert "duckduckgo_search" in names
    assert "tavily_search" not in names
    assert r["data"]["count"] == len(r["data"]["tools"])
    assert r["data"]["unknown_names"] == []


@pytest.mark.asyncio
async def test_list_tools_filter_and_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _refresh_registry_without_tavily(monkeypatch)
    r = await execute_builtin(
        "list_tools",
        {"names": ["duckduckgo_search", "nonexistent_tool", "duckduckgo_search"]},
    )
    assert r["ok"] is True
    assert [t["name"] for t in r["data"]["tools"]] == ["duckduckgo_search"]
    assert r["data"]["unknown_names"] == ["nonexistent_tool"]


@pytest.mark.asyncio
async def test_duckduckgo_search_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.modules.tools.builtin_lc import builtin_lc_tools_by_name

    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()

    tool = builtin_lc_tools_by_name()["duckduckgo_search"]

    def _fake_run(_self: object, query: str, run_manager: object | None = None) -> str:
        return f"stub:{query}"

    monkeypatch.setattr(type(tool), "_run", _fake_run)

    r = await execute_builtin("duckduckgo_search", {"query": "forgeagent"})
    assert r["ok"] is True
    assert "stub:forgeagent" in str(r["data"])
