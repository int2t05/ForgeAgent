"""应用设置 REST 模型（可暴露、可写的非密钥子集）。"""

from typing import Any

from pydantic import BaseModel, Field


class SettingsPublic(BaseModel):
    """GET/PUT 对外字段：MCP 服务元数据列表与 Skills 搜索路径。"""

    mcp: list[Any] = Field(default_factory=list)
    skills_paths: list[str] = Field(default_factory=list)


class SettingsUpdate(SettingsPublic):
    """PUT /settings 请求体；服务端需拒绝密钥类键名。"""


class SettingsUpdateResponse(BaseModel):
    """PUT /settings 响应。"""

    ok: bool = True
