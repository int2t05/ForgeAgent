"""进程内覆盖层：API 持久化的 Agent 工作区根字符串。

优先于环境变量 ``AGENT_WORKSPACE_ROOT``；由 ``tool_registry.refresh`` 写入，供 ``Settings.resolved_agent_workspace_path`` 读取。
"""

from __future__ import annotations

_explicit_workspace_root: str | None = None


def set_explicit_workspace_root(path: str | None) -> None:
    """写入或清除覆盖根路径；空串与 None 均视为清除。"""
    global _explicit_workspace_root
    if path is None:
        _explicit_workspace_root = None
        return
    s = str(path).strip()
    _explicit_workspace_root = s if s else None


def get_explicit_workspace_root() -> str | None:
    """读取当前覆盖路径；未设置则 None（走 env / 默认仓库根）。"""
    return _explicit_workspace_root
