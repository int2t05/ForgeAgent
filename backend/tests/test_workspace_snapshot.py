"""工作区路径解析与列举（/api/v1/workspace 共用逻辑）。"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.shared.workspace_snapshot import (
    WorkspacePathError,
    build_workspace_browser_state,
    resolve_workspace_list_dir,
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_list_root_and_subdirectory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    s = get_settings()
    (tmp_path / "alpha.txt").write_text("x", encoding="utf-8")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "beta.txt").write_text("y", encoding="utf-8")

    root_st = build_workspace_browser_state(s, None)
    assert root_st["parent_path"] is None
    assert root_st["current_path"] == root_st["workspace_root"]
    names = {e["name"] for e in root_st["workspace_listing"]}
    assert "alpha.txt" in names and "nested" in names

    sub_st = build_workspace_browser_state(s, str(sub.resolve()))
    assert sub_st["parent_path"] == str(tmp_path.resolve())
    assert sub_st["current_path"] == str(sub.resolve())
    assert any(e["name"] == "beta.txt" and not e["is_dir"] for e in sub_st["workspace_listing"])


def test_reject_outside_workspace(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(tmp_path))
    s = get_settings()
    outside = tmp_path.parent
    with pytest.raises(WorkspacePathError):
        resolve_workspace_list_dir(s, str(outside.resolve()))
