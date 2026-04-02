"""设置 REST（非密钥：MCP 元数据与 Skills 路径等）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.modules.tools.skill_sources import validate_skill_directory_paths
from app.schemas.settings import (
    SettingsPatch,
    SettingsPublic,
    SkillPathCheckItem,
    SkillPathsValidateBody,
    SkillPathsValidateResponse,
    SettingsUpdate,
    SettingsUpdateResponse,
)
from app.services import settings_service
from app.modules.tools.registry import tool_registry

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsPublic)
async def get_settings(db: AsyncSession = Depends(get_db)) -> SettingsPublic:
    """读取 settings_kv 中允许暴露的字段并反序列化为结构化响应。"""
    return await settings_service.get_settings_public(db)


@router.put("", response_model=SettingsUpdateResponse)
async def put_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingsUpdateResponse:
    """更新非敏感配置；拒绝体中出现疑似密钥字段名。"""
    result = await settings_service.update_settings(db, body)
    await tool_registry.refresh(db)
    return result


@router.patch("", response_model=SettingsUpdateResponse)
async def patch_settings(
    body: SettingsPatch,
    db: AsyncSession = Depends(get_db),
) -> SettingsUpdateResponse:
    """部分更新设置（未传字段保持不变）。"""
    result = await settings_service.patch_settings(db, body)
    await tool_registry.refresh(db)
    return result


@router.delete("", response_model=SettingsUpdateResponse)
async def delete_settings(db: AsyncSession = Depends(get_db)) -> SettingsUpdateResponse:
    """将可 API 读写的设置恢复为空列表（非密钥项）。"""
    result = await settings_service.reset_settings(db)
    await tool_registry.refresh(db)
    return result


@router.post("/skills/validate", response_model=SkillPathsValidateResponse)
async def validate_skill_paths(body: SkillPathsValidateBody) -> SkillPathsValidateResponse:
    """检查 Skill 目录是否存在且含 ``SKILL.md`` / ``skill.md``（可先于保存设置调用）。"""
    raw = [str(p).strip() for p in body.paths if str(p).strip()]
    rows = validate_skill_directory_paths(raw)
    items = [SkillPathCheckItem(**r) for r in rows]
    all_ok = bool(items) and all(it.ok for it in items)
    return SkillPathsValidateResponse(items=items, all_ok=all_ok)
