"""settings_kv 键值表数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import SettingsKV


async def get_value(session: AsyncSession, key: str) -> SettingsKV | None:
    """按键读取单行配置，不存在返回 None。"""
    stmt = select(SettingsKV).where(SettingsKV.key == key)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_value(session: AsyncSession, key: str, value_json: str) -> SettingsKV:
    """存在则更新 value_json，不存在则插入；ORM onupdate 自动刷新 updated_at。"""
    existing = await get_value(session, key)
    if existing is None:
        row = SettingsKV(key=key, value_json=value_json)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row
    existing.value_json = value_json
    await session.flush()
    await session.refresh(existing)
    return existing
