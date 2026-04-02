"""Skill 目录：仅提供 ``SKILL.md`` 与规划器 ``skill_imports`` 解析（无 HTTP 工具调用）。"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKILL_MD_NAMES: tuple[str, ...] = ("SKILL.md", "skill.md")
_DEFAULT_SKILL_IMPORT_MAX_TOTAL = 48_000
_DEFAULT_SKILL_IMPORT_MAX_PER_DIR = 16_000


def _find_skill_md(skill_root: Path) -> Path | None:
    """返回 skill 根目录下存在的 SKILL.md 路径（大小写备选），不存在则 None。"""
    for name in _SKILL_MD_NAMES:
        candidate = skill_root / name
        if candidate.is_file():
            return candidate
    return None


def skill_import_context_from_paths(
    paths: list[str],
    *,
    max_total_chars: int = _DEFAULT_SKILL_IMPORT_MAX_TOTAL,
    max_per_skill_chars: int = _DEFAULT_SKILL_IMPORT_MAX_PER_DIR,
) -> str:
    """扫描给定目录路径，读取 **SKILL.md** 并拼接为一段上下文（供执行步 HumanMessage 注入）。"""
    sections: list[str] = []
    max_total = max(64, int(max_total_chars))
    per_cap = max(32, int(max_per_skill_chars))

    for p in paths:
        root = Path(p).expanduser()
        if not root.is_dir():
            continue
        md_path = _find_skill_md(root)
        if md_path is None:
            continue
        try:
            raw = md_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            logger.warning("无法读取 Skill 说明文件: %s", md_path)
            continue
        if not raw:
            continue
        label = str(root.name).strip() or str(root)
        body = raw if len(raw) <= per_cap else raw[:per_cap] + "\n\n[… truncated …]"
        sections.append(f"### Skill folder: {label}\n\n{body}")

    if not sections:
        return ""

    merged = "\n\n---\n\n".join(sections)
    if len(merged) > max_total:
        merged = merged[:max_total] + "\n\n[… skill import truncated …]"
        logger.warning(
            "Skill SKILL.md 合并长度超过 max_total_chars=%s，已截断",
            max_total,
        )
    return merged


def validate_skill_directory_paths(paths: list[str]) -> list[dict[str, Any]]:
    """校验路径是否为 Skill 根目录（存在、为目录、含 ``SKILL.md`` 或 ``skill.md``）。空行跳过。"""
    rows: list[dict[str, Any]] = []
    for raw in paths:
        line = str(raw).strip()
        if not line:
            continue
        p = Path(line).expanduser()
        try:
            resolved = str(p.resolve(strict=False))
        except (OSError, ValueError):
            resolved = str(p)
        if not p.exists():
            rows.append(
                {
                    "input_path": line,
                    "resolved_path": resolved,
                    "is_directory": False,
                    "has_skill_md": False,
                    "skill_md_filename": None,
                    "ok": False,
                    "message": "路径不存在",
                }
            )
            continue
        if not p.is_dir():
            rows.append(
                {
                    "input_path": line,
                    "resolved_path": resolved,
                    "is_directory": False,
                    "has_skill_md": False,
                    "skill_md_filename": None,
                    "ok": False,
                    "message": "不是目录",
                }
            )
            continue
        md = _find_skill_md(p)
        if md is None:
            rows.append(
                {
                    "input_path": line,
                    "resolved_path": resolved,
                    "is_directory": True,
                    "has_skill_md": False,
                    "skill_md_filename": None,
                    "ok": False,
                    "message": "目录内未找到 SKILL.md 或 skill.md",
                }
            )
            continue
        rows.append(
            {
                "input_path": line,
                "resolved_path": resolved,
                "is_directory": True,
                "has_skill_md": True,
                "skill_md_filename": md.name,
                "ok": True,
                "message": f"已找到 {md.name}",
            }
        )
    return rows


def resolve_planner_skill_imports(
    tokens: Sequence[str],
    configured_paths: Sequence[str],
) -> list[str]:
    """将规划器给出的 skill 标识解析为已配置目录路径（``expanduser`` 后字符串，保序去重）。

    匹配规则：先精确匹配已配置路径；否则按目录名（basename）匹配，仅当唯一命中时采纳；否则记警告并跳过。
    """
    roots = [str(Path(p).expanduser()) for p in configured_paths if str(p).strip()]
    root_set = set(roots)
    by_name: dict[str, list[str]] = {}
    for r in roots:
        by_name.setdefault(Path(r).name, []).append(r)
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        t = str(tok).strip()
        if not t:
            continue
        cand = str(Path(t).expanduser())
        chosen: str | None = None
        if cand in root_set:
            chosen = cand
        else:
            name = Path(t).name
            matches = by_name.get(name, [])
            if len(matches) == 1:
                chosen = matches[0]
            elif len(matches) > 1:
                logger.warning(
                    "skill_imports 条目 %r 对应多个已配置目录，已忽略",
                    t,
                )
            else:
                logger.warning(
                    "skill_imports 条目 %r 未匹配任何已配置 skill 目录，已忽略",
                    t,
                )
        if chosen and chosen not in seen:
            seen.add(chosen)
            out.append(chosen)
    return out
