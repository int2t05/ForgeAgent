"""forge_file_tools：工作区读写的行区间与 max_chars 行为。"""

import pytest

from app.core.config import get_settings
from app.modules.tools.builtin_executor import execute_builtin


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """将 Agent 工作区指到临时目录，避免触碰仓库内默认工作区。"""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_read_file_full_and_lines(isolated_workspace) -> None:
    p = isolated_workspace / "t.txt"
    p.write_text("L1\nL2\nL3\n", encoding="utf-8")

    r0 = await execute_builtin("read_file", {"file_path": "t.txt"})
    assert r0["ok"] is True
    assert r0["data"] == "L1\nL2\nL3\n"

    r1 = await execute_builtin("read_file", {"file_path": "t.txt", "end_line": 2})
    assert r1["ok"] is True
    assert r1["data"] == "L1\nL2\n"

    r2 = await execute_builtin("read_file", {"file_path": "t.txt", "start_line": 2})
    assert r2["ok"] is True
    assert r2["data"] == "L2\nL3\n"

    r3 = await execute_builtin(
        "read_file", {"file_path": "t.txt", "start_line": 2, "end_line": 2}
    )
    assert r3["ok"] is True
    assert r3["data"] == "L2\n"


@pytest.mark.asyncio
async def test_read_file_max_chars(isolated_workspace) -> None:
    p = isolated_workspace / "long.txt"
    p.write_text("abcdefghij", encoding="utf-8")
    r = await execute_builtin("read_file", {"file_path": "long.txt", "max_chars": 4})
    assert r["ok"] is True
    assert "abcd" in r["data"]
    assert "截断" in r["data"]


@pytest.mark.asyncio
async def test_write_file_replace_lines(isolated_workspace) -> None:
    p = isolated_workspace / "e.txt"
    p.write_text("a\nb\nc\nd\n", encoding="utf-8")
    r = await execute_builtin(
        "write_file",
        {
            "file_path": "e.txt",
            "text": "X\n",
            "start_line": 2,
            "end_line": 3,
        },
    )
    assert r["ok"] is True
    assert "replaced" in str(r["data"]).lower() or "updated" in str(r["data"]).lower()
    assert p.read_text(encoding="utf-8") == "a\nX\nd\n"


@pytest.mark.asyncio
async def test_write_file_append_and_validation(isolated_workspace) -> None:
    p = isolated_workspace / "a.txt"
    await execute_builtin("write_file", {"file_path": "a.txt", "text": "hi"})
    r = await execute_builtin(
        "write_file", {"file_path": "a.txt", "text": "\nmore", "append": True}
    )
    assert r["ok"] is True
    assert "hi\nmore" in p.read_text(encoding="utf-8")

    bad = await execute_builtin(
        "write_file",
        {
            "file_path": "a.txt",
            "text": "x",
            "append": True,
            "start_line": 1,
            "end_line": 1,
        },
    )
    assert bad["ok"] is False


@pytest.mark.asyncio
async def test_read_file_denied_outside_root(isolated_workspace) -> None:
    r = await execute_builtin(
        "read_file", {"file_path": str(isolated_workspace.parent / "secret.txt")}
    )
    assert r["ok"] is True
    assert "Access denied" in str(r["data"]) or "denied" in str(r["data"]).lower()
