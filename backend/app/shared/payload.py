"""事件与 API 共用的 payload_json 安全解析。"""

from __future__ import annotations

import json


def payload_json_to_dict(raw: str | None) -> dict | None:
    """将 JSON 字符串解析为 dict；空串或非对象则返回 None。"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
