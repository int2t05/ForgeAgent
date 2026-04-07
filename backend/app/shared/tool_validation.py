"""工具参数校验：防止工具调用幻觉。

通过 Pydantic schema 验证工具参数，确保 LLM 输出的工具调用符合工具定义。
"""

from __future__ import annotations

import logging
from typing import Any, get_type_hints

from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)


class ToolValidationError(Exception):
    """工具参数校验错误。"""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


def validate_tool_args(
    tool_name: str,
    args: dict[str, Any] | None,
    schema: type[BaseModel] | dict[str, Any] | None,
) -> dict[str, Any]:
    """验证工具参数。

    Args:
        tool_name: 工具名称（用于错误信息）
        args: 工具参数字典
        schema: Pydantic 模型类或 JSON Schema 字典

    Returns:
        验证后的参数字典

    Raises:
        ToolValidationError: 参数校验失败
    """
    if schema is None:
        return args or {}

    if isinstance(schema, dict):
        # JSON Schema 验证
        return _validate_with_json_schema(tool_name, args or {}, schema)

    # Pydantic 模型验证
    return _validate_with_pydantic(tool_name, args or {}, schema)


def _validate_with_pydantic(
    tool_name: str,
    args: dict[str, Any],
    schema_cls: type[BaseModel],
) -> dict[str, Any]:
    """使用 Pydantic 模型验证参数。"""
    try:
        validated = schema_cls.model_validate(args)
        return validated.model_dump(mode="json")
    except ValidationError as e:
        errors = e.errors()
        error_messages = []
        for err in errors:
            loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
            msg = err.get("msg", "invalid")
            error_messages.append(f"{loc}: {msg}" if loc else msg)

        raise ToolValidationError(
            f"工具 {tool_name} 参数校验失败: {'; '.join(error_messages)}",
            errors=errors,
        )


def _validate_with_json_schema(
    tool_name: str,
    args: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """使用 JSON Schema 验证参数。"""
    # 简单的必填字段检查
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in args or args[field_name] is None:
            raise ToolValidationError(
                f"工具 {tool_name} 缺少必填参数: {field_name}",
                errors=[{"loc": (field_name,), "msg": "field required", "type": "missing"}],
            )

    # 类型检查
    properties = schema.get("properties", {})
    for field_name, value in args.items():
        if field_name in properties:
            expected_type = properties[field_name].get("type")
            if expected_type and not _check_type(value, expected_type):
                logger.warning(
                    "工具 %s 参数 %s 类型不匹配: 期望 %s, 实际 %s",
                    tool_name,
                    field_name,
                    expected_type,
                    type(value).__name__,
                )

    return args


def _check_type(value: Any, expected_type: str) -> bool:
    """检查值是否符合预期类型。"""
    if value is None:
        return True  # None 视为可选

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    expected = type_map.get(expected_type)
    if expected is None:
        return True

    if isinstance(expected, tuple):
        return isinstance(value, expected)
    return isinstance(value, expected)


def sanitize_tool_args(
    tool_name: str,
    args: dict[str, Any],
    allowed_keys: list[str] | None = None,
) -> dict[str, Any]:
    """清理工具参数，移除未知或危险的键。

    Args:
        tool_name: 工具名称
        args: 原始参数
        allowed_keys: 允许的键列表，None 表示不限制

    Returns:
        清理后的参数
    """
    if allowed_keys is None:
        return args

    sanitized = {}
    for key in allowed_keys:
        if key in args:
            sanitized[key] = args[key]

    if len(sanitized) != len(args):
        removed = set(args.keys()) - set(sanitized.keys())
        logger.debug(
            "工具 %s 参数已清理，移除未知键: %s",
            tool_name,
            removed,
        )

    return sanitized


class ToolArgsValidator:
    """工具参数验证器管理器。

    维护工具 schema 注册表，用于验证工具调用。
    """

    def __init__(self):
        self._schemas: dict[str, type[BaseModel] | dict[str, Any]] = {}

    def register_schema(
        self,
        tool_name: str,
        schema: type[BaseModel] | dict[str, Any],
    ) -> None:
        """注册工具 schema。"""
        self._schemas[tool_name] = schema

    def get_schema(
        self, tool_name: str
    ) -> type[BaseModel] | dict[str, Any] | None:
        """获取工具 schema。"""
        return self._schemas.get(tool_name)

    def validate(
        self,
        tool_name: str,
        args: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """验证工具参数。"""
        schema = self.get_schema(tool_name)
        return validate_tool_args(tool_name, args, schema)

    def validate_or_raise(
        self,
        tool_name: str,
        args: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """验证工具参数，失败则抛出异常。"""
        schema = self.get_schema(tool_name)
        if schema is None:
            logger.warning(
                "工具 %s 未注册 schema，跳过验证",
                tool_name,
            )
            return args or {}

        return validate_tool_args(tool_name, args, schema)


# 全局验证器实例
_tool_args_validator = ToolArgsValidator()


def get_tool_args_validator() -> ToolArgsValidator:
    """获取全局工具参数验证器。"""
    return _tool_args_validator


def register_tool_schema(
    tool_name: str,
    schema: type[BaseModel] | dict[str, Any],
) -> None:
    """注册工具 schema 到全局验证器。"""
    _tool_args_validator.register_schema(tool_name, schema)
