"""应用设置 REST 模型（可暴露、可写的非密钥子集）。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

ExecutionMode = Literal["auto", "confirm", "learn"]


class SettingsPatch(BaseModel):
    """PATCH /settings：仅覆盖提供的字段，与 GET 形状一致。"""

    mcp: list[Any] | None = None
    skills_paths: list[str] | None = None
    agent_workspace_root: str | None = None
    execution_mode: ExecutionMode | None = Field(
        default=None,
        description="工具执行模式：auto(全自动) / confirm(每次确认) / learn(记录后自动放行)",
    )
    approved_tool_patterns: list[str] | None = Field(
        default=None,
        description="learn 模式下已批准的工具名列表（仅 learn 模式生效）",
    )


class SettingsPublic(BaseModel):
    """GET/PUT 对外字段：MCP、Skills、Agent 工作区根、执行模式（非密钥）。"""

    mcp: list[Any] = Field(default_factory=list)
    skills_paths: list[str] = Field(default_factory=list)
    agent_workspace_root: str | None = Field(
        None,
        description="工作区绝对路径或相对 monorepo 的路径；空则使用环境变量 AGENT_WORKSPACE_ROOT",
    )
    execution_mode: ExecutionMode = Field(
        "auto",
        description="工具执行策略：auto=全自动, confirm=每次人工确认, learn=首次确认后自动放行",
    )
    approved_tool_patterns: list[str] = Field(
        default_factory=list,
        description="learn 模式下已批准放行的敏感工具名列表",
    )


class SettingsUpdate(SettingsPublic):
    """PUT /settings 请求体；服务端需拒绝密钥类键名。"""


class SettingsUpdateResponse(BaseModel):
    """PUT /settings 响应。"""

    ok: bool = True


class SkillPathsValidateBody(BaseModel):
    """POST /settings/skills/validate 请求体（可与已保存设置不一致，用于保存前检查）。"""

    paths: list[str] = Field(default_factory=list)


class SkillPathCheckItem(BaseModel):
    """单条 Skill 目录校验结果。"""

    input_path: str
    resolved_path: str = ""
    is_directory: bool = False
    has_skill_md: bool = False
    skill_md_filename: str | None = None
    ok: bool = False
    message: str = ""


class SkillPathsValidateResponse(BaseModel):
    """POST /settings/skills/validate 响应。"""

    items: list[SkillPathCheckItem] = Field(default_factory=list)
    all_ok: bool = Field(
        False,
        description="items 非空且全部 ok；无有效路径时为 False",
    )
