"""Skill 目录校验 API 与纯函数。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.modules.tools.skill_sources import validate_skill_directory_paths


def test_validate_skill_directory_paths_happy_and_misses() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "has_md"
        good.mkdir()
        (good / "SKILL.md").write_text("# ok", encoding="utf-8")
        nodir = Path(tmp) / "nope_missing"
        bad = Path(tmp) / "file_not_dir.txt"
        bad.write_text("x", encoding="utf-8")
        empty_dir = Path(tmp) / "no_md"
        empty_dir.mkdir()

        rows = validate_skill_directory_paths(
            [str(good), str(nodir), str(bad), str(empty_dir), "  ", ""],
        )
        assert len(rows) == 4
        assert rows[0]["ok"] is True
        assert rows[0]["has_skill_md"] is True
        assert rows[1]["message"] == "路径不存在"
        assert rows[2]["message"] == "不是目录"
        assert rows[3]["message"] == "目录内未找到 SKILL.md 或 skill.md"


def test_post_settings_skills_validate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sk = Path(tmp) / "s"
        sk.mkdir()
        (sk / "skill.md").write_text("x", encoding="utf-8")
        client = TestClient(app)
        r = client.post(
            "/api/v1/settings/skills/validate",
            json={"paths": [str(sk), "/nonexistent_dir_xyz"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["all_ok"] is False
        assert len(data["items"]) == 2
        ok_one = next(x for x in data["items"] if x["ok"])
        assert ok_one["skill_md_filename"] and ok_one["skill_md_filename"].lower() == "skill.md"
