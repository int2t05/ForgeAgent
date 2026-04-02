"""SKILL.md 导入为执行上下文（与 manifest 工具无关）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.modules.tools.skill_sources import (
    resolve_planner_skill_imports,
    skill_import_context_from_paths,
)


def test_skill_import_reads_skill_md_and_skips_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "has_skill"
        a.mkdir()
        (a / "SKILL.md").write_text("Hello from skill A", encoding="utf-8")
        b = Path(tmp) / "no_md"
        b.mkdir()
        out = skill_import_context_from_paths([str(a), str(b), "/nonexistent/dir"])
        assert "Hello from skill A" in out
        assert "has_skill" in out
        assert out.count("### Skill folder:") == 1


def test_resolve_planner_skill_imports_by_basename_and_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        my = Path(tmp) / "my_skill"
        my.mkdir()
        other = Path(tmp) / "alt"
        other.mkdir()
        base = str(my)
        cfg = [base, str(other)]
        assert resolve_planner_skill_imports(["my_skill"], cfg) == [base]
        assert resolve_planner_skill_imports([base], cfg) == [base]


def test_skill_import_respects_total_cap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s"
        p.mkdir()
        (p / "SKILL.md").write_text("x" * 500, encoding="utf-8")
        out = skill_import_context_from_paths([str(p)], max_total_chars=200)
        assert len(out) <= 260
        assert "truncated" in out
