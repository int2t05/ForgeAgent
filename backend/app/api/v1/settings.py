"""设置 REST（非密钥：MCP 元数据与 Skills 路径等）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.settings import SettingsPublic, SettingsUpdate, SettingsUpdateResponse
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsPublic)
async def get_settings(db: AsyncSession = Depends(get_db)) -> SettingsPublic:
    """读取 settings_kv 中允许暴露的字段并反序列化为结构化响应。"""
    # 1. 按固定 key 读取 mcp / skills_paths
    # 2. 缺省或损坏 JSON 时回退为空列表
    return await settings_service.get_settings_public(db)


@router.put("", response_model=SettingsUpdateResponse)
async def put_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingsUpdateResponse:
    """更新非敏感配置；拒绝体中出现疑似密钥字段名。"""
    # 1. 递归校验键名不含 api_key 等片段
    # 2. upsert 写入 settings_kv
    # 3. 返回 { ok: true }
    return await settings_service.update_settings(db, body)
