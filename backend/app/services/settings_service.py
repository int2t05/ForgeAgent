"""对外可写设置：MCP、Skills、Agent 工作区根（settings_kv）；拒绝密钥形状字段名。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppHTTPException
from app.repositories import settings_repository
from app.schemas.settings import (
    SettingsPatch,
    SettingsPublic,
    SettingsUpdate,
    SettingsUpdateResponse,
)

_SETTINGS_KEY_MCP = "mcp"
_SETTINGS_KEY_SKILLS = "skills_paths"
_SETTINGS_KEY_WORKSPACE = "agent_workspace_root"

_FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "bearer",
)


def _optional_workspace_root_from_row(value_json: str | None) -> str | None:
    """解析 settings_kv 中单字符串或 null；损坏或非字符串则视为未配置。"""
    if not value_json:
        return None
    try:
        v = json.loads(value_json)
    except json.JSONDecodeError:
        return None
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return None


def _json_list_from_row(value_json: str | None) -> list[Any]:
    """将 settings_kv 中的 JSON 文本解析为列表，非法或空则返回 []。"""
    if not value_json:
        return []
    try:
        p = json.loads(value_json)
        return p if isinstance(p, list) else []
    except json.JSONDecodeError:
        return []


def _walk_no_secret_keys(obj: Any, *, _parent_key: str | None = None) -> None:
    """深度优先遍历 JSON 可序列化结构，发现可疑键名则抛错。

    MCP 的 ``headers`` / ``env`` 子对象中为合法 HTTP 头名与环境变量名，
    不再按子串匹配拦截（否则 ``Authorization``、``MYTOKEN``、``OPENAI_API_KEY`` 等无法保存）。
    """
    if isinstance(obj, dict):
        parent_lk = (_parent_key or "").lower()
        skip_key_names = parent_lk in ("headers", "env")
        for k, v in obj.items():
            lk = str(k).lower()
            if not skip_key_names and any(
                fragment in lk for fragment in _FORBIDDEN_KEY_FRAGMENTS
            ):
                raise AppHTTPException(
                    f"禁止在设置中写入字段: {k}",
                    code="SECRET_FIELD",
                    status_code=400,
                )
            _walk_no_secret_keys(v, _parent_key=str(k))
    elif isinstance(obj, list):
        for item in obj:
            _walk_no_secret_keys(item, _parent_key=None)


async def get_settings_public(db: AsyncSession) -> SettingsPublic:
    """读取 settings_kv 中与 GET /settings 对应的结构化字段。"""
    # 1. 读行
    mcp_row = await settings_repository.get_value(db, _SETTINGS_KEY_MCP)
    skills_row = await settings_repository.get_value(db, _SETTINGS_KEY_SKILLS)
    ws_row = await settings_repository.get_value(db, _SETTINGS_KEY_WORKSPACE)
    # 2. 解析
    mcp = _json_list_from_row(mcp_row.value_json if mcp_row else None)
    skills_raw = _json_list_from_row(skills_row.value_json if skills_row else None)
    skills_paths = [str(x) for x in skills_raw]
    agent_workspace_root = _optional_workspace_root_from_row(
        ws_row.value_json if ws_row else None,
    )
    return SettingsPublic(
        mcp=mcp,
        skills_paths=skills_paths,
        agent_workspace_root=agent_workspace_root,
    )


async def update_settings(
    db: AsyncSession, body: SettingsUpdate
) -> SettingsUpdateResponse:
    """校验请求体并写回 settings_kv（MCP、Skills、工作区根）。"""
    # 1. 禁止可疑键名
    _walk_no_secret_keys(body.model_dump())
    # 2. 分项 upsert
    await settings_repository.upsert_value(
        db, _SETTINGS_KEY_MCP, json.dumps(body.mcp, ensure_ascii=False)
    )
    await settings_repository.upsert_value(
        db,
        _SETTINGS_KEY_SKILLS,
        json.dumps(body.skills_paths, ensure_ascii=False),
    )
    await settings_repository.upsert_value(
        db,
        _SETTINGS_KEY_WORKSPACE,
        json.dumps(body.agent_workspace_root, ensure_ascii=False),
    )
    return SettingsUpdateResponse()


async def patch_settings(
    db: AsyncSession, body: SettingsPatch
) -> SettingsUpdateResponse:
    """读取当前值后与 body 合并，再走 update_settings 全量写回。"""
    current = await get_settings_public(db)
    new_mcp = body.mcp if body.mcp is not None else current.mcp
    new_paths = (
        body.skills_paths if body.skills_paths is not None else current.skills_paths
    )
    if body.agent_workspace_root is not None:
        new_ws = body.agent_workspace_root.strip() or None
    else:
        new_ws = current.agent_workspace_root
    merged = SettingsUpdate(
        mcp=new_mcp,
        skills_paths=new_paths,
        agent_workspace_root=new_ws,
    )
    return await update_settings(db, merged)


async def reset_settings(db: AsyncSession) -> SettingsUpdateResponse:
    """清空对外 MCP、Skills 与工作区根（回退环境变量），仅影响可 API 读写的键。"""
    await update_settings(
        db,
        SettingsUpdate(mcp=[], skills_paths=[], agent_workspace_root=None),
    )
    return SettingsUpdateResponse()
