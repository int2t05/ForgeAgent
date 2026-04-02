"""工作区路径校验与单层目录列举。

供 HTTP GET /workspace、step_start 事件嵌入根目录快照及前端资源管理器侧栏；与 ``Settings.resolved_agent_workspace_path`` 所指根一致。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import Settings

WORKSPACE_LISTING_MAX = 200


class WorkspacePathError(ValueError):
    """请求路径不在工作区内、不存在或非目录时抛出。"""


def _workspace_root_resolved(settings: Settings) -> Path:
    """返回已 resolve 的工作区根路径。"""
    try:
        return settings.resolved_agent_workspace_path().resolve()
    except OSError as e:
        raise WorkspacePathError("无法解析工作区根路径") from e


def resolve_workspace_list_dir(settings: Settings, path_param: str | None) -> Path:
    """解析出待列举目录：必须在根下且为已存在文件夹；省略 path_param 时返回根。"""
    root_resolved = _workspace_root_resolved(settings)
    # 1. 未传路径则列举根
    if path_param is None or not str(path_param).strip():
        return root_resolved
    raw = str(path_param).strip()
    candidate = Path(raw)
    # 2. 得到候选绝对路径
    try:
        resolved = candidate.resolve() if candidate.is_absolute() else (root_resolved / raw).resolve()
    except (OSError, RuntimeError) as e:
        raise WorkspacePathError("路径无效") from e
    # 3. 约束在根之下
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise WorkspacePathError("路径必须位于 Agent 工作区内")
    # 4. 必须是已存在目录
    if not resolved.exists():
        raise WorkspacePathError("目录不存在")
    if not resolved.is_dir():
        raise WorkspacePathError("不是文件夹")
    return resolved


def _entry_dict(p: Path) -> dict[str, Any]:
    """单文件系统条目序列化为 API 字典（含可选文件大小）。"""
    size_bytes: int | None = None
    if p.is_file():
        try:
            size_bytes = int(p.stat().st_size)
        except OSError:
            size_bytes = None
    return {
        "name": p.name,
        "path": str(p.resolve()),
        "is_dir": p.is_dir(),
        "size_bytes": size_bytes,
    }


def _list_directory_entries(list_dir: Path) -> tuple[list[dict[str, Any]], bool]:
    """读取目录下子项，文件夹优先、名称不区分大小写排序；超出 WORKSPACE_LISTING_MAX 则截断。"""
    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        kids = sorted(
            list_dir.iterdir(),
            key=lambda x: (not x.is_dir(), x.name.lower()),
        )
    except OSError:
        kids = []
    for p in kids:
        if len(entries) >= WORKSPACE_LISTING_MAX:
            truncated = True
            break
        try:
            entries.append(_entry_dict(p))
        except OSError:
            continue
    return entries, truncated


def build_workspace_browser_state(
    settings: Settings,
    path_param: str | None,
) -> dict[str, Any]:
    """构造单层浏览态：根、当前路径、上级路径、条目列表及是否截断。"""
    root_resolved = _workspace_root_resolved(settings)
    root_s = str(root_resolved)
    current = resolve_workspace_list_dir(settings, path_param)
    current_s = str(current)
    root_r = root_resolved.resolve()
    cur_r = current.resolve()
    # 1. 计算上级路径（根目录无上级）
    if cur_r == root_r:
        parent: str | None = None
    else:
        try:
            par = current.parent.resolve()
            par.relative_to(root_r)
        except (ValueError, OSError) as e:
            raise WorkspacePathError("无法解析上级目录") from e
        parent = str(par)
    # 2. 列举当前目录
    listing, truncated = _list_directory_entries(current)
    return {
        "workspace_root": root_s,
        "current_path": current_s,
        "parent_path": parent,
        "workspace_listing": listing,
        "workspace_listing_truncated": truncated,
    }


def build_workspace_snapshot(settings: Settings) -> dict[str, Any]:
    """根目录一级快照（字段供 step_start 等事件嵌入，不含 current_path/parent_path）。"""
    st = build_workspace_browser_state(settings, None)
    return {
        "workspace_root": st["workspace_root"],
        "workspace_listing": st["workspace_listing"],
        "workspace_listing_truncated": st["workspace_listing_truncated"],
    }


# 旧导入名保留，避免未合并分支在运行时 NameError
_workspace_step_envelope = build_workspace_snapshot
