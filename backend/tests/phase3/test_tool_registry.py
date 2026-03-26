"""阶段3：工具注册表 + MCP mock + Skills（见 tests/docs/phase3.md）。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXAMPLE_SKILL_DIR = _REPO_ROOT / "skills" / "example_skill"


@pytest.mark.phase3
def test_tools_include_builtin_mcp_and_skill_after_settings(client: TestClient) -> None:
    """PUT 设置 mock MCP 与 Skills 路径后，GET /tools 含三种 source。"""
    body = {
        "mcp": [
            {
                "name": "mock-svr",
                "enabled": True,
                "transport": "mock",
                "tools": [
                    {
                        "name": "mock_mcp_add",
                        "description": "文档化 mock：加法器占位",
                        "read_only": True,
                    }
                ],
            }
        ],
        "skills_paths": [str(_EXAMPLE_SKILL_DIR.resolve())],
    }
    # 1. 持久化设置并触发注册表刷新
    r = client.put("/api/v1/settings", json=body)
    assert r.status_code == 200
    # 2. 拉取工具列表
    r = client.get("/api/v1/tools")
    assert r.status_code == 200
    tools = r.json()["tools"]
    by_name = {t["name"]: t for t in tools}
    # 3. 内置仍存在且优先占位
    assert "echo" in by_name
    assert by_name["echo"]["source"] == "builtin"
    # 4. MCP mock 已进入注册表
    assert "mock_mcp_add" in by_name
    assert by_name["mock_mcp_add"]["source"] == "mcp"
    # 5. 示例 Skill 声明的工具已进入注册表
    assert "example_skill_greet" in by_name
    assert by_name["example_skill_greet"]["source"] == "skill"


@pytest.mark.phase3
def test_disabled_mcp_server_contributes_no_tools(client: TestClient) -> None:
    """enabled=false 的 MCP 项不产生工具项。"""
    r = client.put(
        "/api/v1/settings",
        json={
            "mcp": [
                {
                    "name": "off",
                    "enabled": False,
                    "transport": "mock",
                    "tools": [{"name": "should_not_appear", "description": "x"}],
                }
            ],
            "skills_paths": [],
        },
    )
    assert r.status_code == 200
    tools = client.get("/api/v1/tools").json()["tools"]
    names = {t["name"] for t in tools}
    assert "should_not_appear" not in names


@pytest.mark.phase3
def test_builtin_wins_on_name_collision(client: TestClient, tmp_path: Path) -> None:
    """同名时内置优先，Skill 中重复名被忽略。"""
    skill_root = tmp_path / "dup_skill"
    skill_root.mkdir()
    (skill_root / "manifest.json").write_text(
        '{"name":"dup","tools":[{"name":"echo","description":"冲突"}]}',
        encoding="utf-8",
    )
    r = client.put(
        "/api/v1/settings",
        json={"mcp": [], "skills_paths": [str(skill_root)]},
    )
    assert r.status_code == 200
    echo_entries = [t for t in client.get("/api/v1/tools").json()["tools"] if t["name"] == "echo"]
    assert len(echo_entries) == 1
    assert echo_entries[0]["source"] == "builtin"
