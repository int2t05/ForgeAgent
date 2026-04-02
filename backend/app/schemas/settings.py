"""应用设置 REST 模型（可暴露、可写的非密钥子集）。"""

from typing import Any

from pydantic import BaseModel, Field


class SettingsPatch(BaseModel):
    """PATCH /settings：仅覆盖提供的字段，与 GET 形状一致。"""

    mcp: list[Any] | None = None
    skills_paths: list[str] | None = None
    agent_workspace_root: str | None = None


class SettingsPublic(BaseModel):
    """GET/PUT 对外字段：MCP、Skills 与 Agent 工作区根（非密钥）。"""

    mcp: list[Any] = Field(default_factory=list)
    skills_paths: list[str] = Field(default_factory=list)
    agent_workspace_root: str | None = Field(
        None,
        description="工作区绝对路径或相对 monorepo 的路径；空则使用环境变量 AGENT_WORKSPACE_ROOT",
    )


class SettingsUpdate(SettingsPublic):
    """PUT /settings 请求体；服务端需拒绝密钥类键名。"""


class SettingsUpdateResponse(BaseModel):
    """PUT /settings 响应。"""

    ok: bool = True
