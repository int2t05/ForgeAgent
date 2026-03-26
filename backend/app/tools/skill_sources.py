"""从 Skills 约定目录解析 manifest.json，映射为 source=skill 的工具元数据。"""

import json
from pathlib import Path
from typing import Any

from app.schemas.tools import ToolItem


def _read_manifest(skill_root: Path) -> dict[str, Any] | None:
    """读取 skill 根目录下的 manifest.json；不存在或非法则返回 None。"""
    manifest = skill_root / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def tools_from_skill_paths(paths: list[str]) -> list[ToolItem]:
    """
    扫描 skills_paths：每项为包含 manifest.json 的目录路径。

    manifest 约定（MVP）：
    - name: Skill 标识
    - tools: [ { "name", "description", "read_only"? } ]
    """
    # 1. 遍历配置的 skills 根路径
    out: list[ToolItem] = []
    for p in paths:
        root = Path(p).expanduser()  # 展开路径中的 ~ 为用户家目录
        if not root.is_dir():
            continue
        data = _read_manifest(root)
        if not data:
            continue
        skill_name = str(data.get("name") or root.name).strip() or root.name
        tool_specs = data.get("tools")
        if not isinstance(tool_specs, list):
            continue
        # 2. 将 manifest.tools 转为 ToolItem，描述中可带上 Skill 名便于排障
        for idx, spec in enumerate(tool_specs):
            if not isinstance(spec, dict):
                continue
            tname = spec.get("name")
            if not tname:
                tname = f"{skill_name}_tool_{idx}"
            tname = str(tname).strip()
            base_desc = str(spec.get("description") or "Skill 声明的工具").strip()
            desc = f"[{skill_name}] {base_desc}"
            out.append(
                ToolItem(
                    name=tname,
                    description=desc,
                    source="skill",
                    read_only=bool(spec.get("read_only", True)),
                )
            )
    # 3. 返回与内置/MCP 相同结构的列表
    return out
