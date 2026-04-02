"""内置工具真实执行（与 ``builtin_lc.builtin_lc_tools_by_name`` 名称一一对应）。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from app.modules.tools.builtin_lc import builtin_lc_tools_by_name

logger = logging.getLogger(__name__)


def _tool_validation_error_message(exc: ValidationError) -> str:
    """将校验错误压缩为适合事件流展示的单行说明。"""
    errs = exc.errors()  # 返回验证错误的详细列表
    if not errs:
        return "参数不符合工具 Schema"
    first = errs[0]
    loc = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
    msg = first.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else str(msg)


async def execute_builtin(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """通过 LangChain ``BaseTool.ainvoke`` 执行内置工具，返回注册表约定的 ok/data/error 结构。"""
    tool = builtin_lc_tools_by_name().get(name)
    if tool is None:
        return {"ok": False, "error": f"未实现的内置工具: {name}"}
    payload = dict(args) if args else {}
    try:
        data = await _ainvoke_builtin(tool, payload)
    except ValidationError as e:
        return {"ok": False, "error": _tool_validation_error_message(e)}
    except Exception:
        logger.exception("builtin tool %s failed", name)
        return {"ok": False, "error": f"内置工具执行异常: {name}"}
    return {"ok": True, "data": data}


async def _ainvoke_builtin(tool: BaseTool, payload: dict[str, Any]) -> Any:
    """
    将计划步骤中的 ``args`` 与 LangChain StructuredTool 对齐。

    先按 ``args_schema`` 做 Pydantic 校验并 ``model_dump`` 为字段名（如 echo 的
    ``message`` → ``text``），再 ``ainvoke``，避免 LC 将原始键原样传入协程导致
    ``TypeError``。
    """
    schema_cls = getattr(tool, "args_schema", None)
    if isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
        validated = schema_cls.model_validate(payload)  # 校验
        canonical: dict[str, Any] = validated.model_dump(mode="json")  # 导出为字典
        return await tool.ainvoke(canonical)
    return await tool.ainvoke(payload)
