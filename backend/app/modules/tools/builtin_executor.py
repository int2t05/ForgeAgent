"""内置工具真实执行（与 list_builtin_tools 名称一一对应）。"""

from __future__ import annotations

from typing import Any


async def execute_builtin(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行已实现的内置工具分支并返回注册表约定的 ok/data/error 结构。"""
    if name == "echo":
        text = args.get("text")
        if text is None:
            text = args.get("message")
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        return {"ok": True, "data": {"echoed": text}}

    if name == "mock_search":
        q = args.get("query", "")
        if not isinstance(q, str):
            q = str(q) if q is not None else ""
        return {
            "ok": True,
            "data": {
                "query": q,
                "results": [
                    {
                        "title": "mock 文档 A",
                        "snippet": f"与「{q or '（空查询）'}」相关的占位摘要（内置 mock_search）。",
                    },
                    {
                        "title": "mock 文档 B",
                        "snippet": "ForgeAgent 执行链路联调用固定结果，可换真实检索后保持 schema。",
                    },
                ],
            },
        }

    return {"ok": False, "error": f"未实现的内置工具: {name}"}
