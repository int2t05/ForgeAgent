"""设置用例服务（工具/MCP 元数据；禁止经 API 写入密钥）。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppHTTPException
from app.repositories import settings_repository
from app.schemas.settings import (
    SettingsPatch,
    SettingsPublic,
    SettingsUpdate,
    SettingsUpdateResponse,
)

_SETTINGS_KEY_MCP = "mcp"
_SETTINGS_KEY_SKILLS = "skills_paths"

_FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "bearer",
)


def _walk_no_secret_keys(obj: Any) -> None:
    """深度优先遍历 JSON 可序列化结构，发现可疑键名则抛错。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if any(fragment in lk for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise AppHTTPException(
                    f"禁止在设置中写入字段: {k}",
                    code="SECRET_FIELD",
                    status_code=400,
                )
            _walk_no_secret_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            _walk_no_secret_keys(item)


async def get_settings_public(db: AsyncSession) -> SettingsPublic:
    """从 settings_kv 组装对外可见的设置 DTO。"""
    mcp_row = await settings_repository.get_value(db, _SETTINGS_KEY_MCP)
    skills_row = await settings_repository.get_value(db, _SETTINGS_KEY_SKILLS)
    mcp: list[Any] = []
    skills_paths: list[str] = []
    # 1. 解析 mcp 列表，失败或类型不对则置空
    if mcp_row:
        try:
            parsed = json.loads(mcp_row.value_json)  # 反序列化
            if isinstance(parsed, list):
                mcp = parsed
        except json.JSONDecodeError:
            mcp = []
    # 2. 解析 skills_paths
    if skills_row:
        try:
            parsed = json.loads(skills_row.value_json)
            if isinstance(parsed, list):
                skills_paths = [str(x) for x in parsed]
        except json.JSONDecodeError:
            skills_paths = []
    # 3. 返回契约模型
    return SettingsPublic(mcp=mcp, skills_paths=skills_paths)


async def update_settings(
    db: AsyncSession, body: SettingsUpdate
) -> SettingsUpdateResponse:
    """校验并持久化设置；与 GET 字段对称。"""
    # 1. 校验请求体树中无禁止键名
    _walk_no_secret_keys(body.model_dump())  # 转为 Python 原生 dict 对象
    # 2. 分别 upsert mcp 与 skills_paths
    await settings_repository.upsert_value(
        db, _SETTINGS_KEY_MCP, json.dumps(body.mcp, ensure_ascii=False)
    )
    await settings_repository.upsert_value(
        db,
        _SETTINGS_KEY_SKILLS,
        json.dumps(body.skills_paths, ensure_ascii=False),
    )
    # 3. 固定响应 ok
    return SettingsUpdateResponse()


async def patch_settings(
    db: AsyncSession, body: SettingsPatch
) -> SettingsUpdateResponse:
    """合并部分字段后写回 settings_kv；未传字段保持原值。"""
    current = await get_settings_public(db)
    new_mcp = body.mcp if body.mcp is not None else current.mcp
    new_paths = (
        body.skills_paths if body.skills_paths is not None else current.skills_paths
    )
    merged = SettingsUpdate(mcp=new_mcp, skills_paths=new_paths)
    return await update_settings(db, merged)


async def reset_settings(db: AsyncSession) -> SettingsUpdateResponse:
    """清空对外 MCP 与 Skills 路径配置（空列表），仅影响可 API 读写的键。"""
    await update_settings(db, SettingsUpdate(mcp=[], skills_paths=[]))
    return SettingsUpdateResponse()
