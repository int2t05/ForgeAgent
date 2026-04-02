"""工具注册表片段：序列化为规划 / ReAct 提示中的【工具目录】块。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.schemas.tools import ToolItem


def tools_catalog_for_prompt(tools: Sequence[ToolItem]) -> str:
    """将注册表工具转为 LLM 可读目录（与 GET /tools 一致）。"""
    catalog: list[dict[str, Any]] = []
    for t in tools:
        entry: dict[str, Any] = {
            "name": t.name,
            "description": t.description,
            "source": t.source,
        }
        if t.read_only is not None:
            entry["read_only"] = t.read_only
        if t.parameters:
            entry["parameters"] = t.parameters
        catalog.append(entry)
    return json.dumps(catalog, ensure_ascii=False, indent=2)
