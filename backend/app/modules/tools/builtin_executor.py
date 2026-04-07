"""内置工具真实执行（与 ``builtin_lc.builtin_lc_tools_by_name`` 名称一一对应）。

支持 ToolContext 传递用户身份信息，通过参数校验防止工具调用幻觉。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.modules.tools.builtin_lc import builtin_lc_tools_by_name
from app.shared.tool_context import ToolContext, get_current_tool_context, set_current_tool_context, with_tool_context
from app.shared.tool_validation import ToolValidationError, get_tool_args_validator

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


def _tool_timeout_sec(name: str, settings: Settings) -> float:
    """按工具类型解析墙钟超时（秒）；与 ``shell`` / ``python_repl`` 既有子进程上限对齐或取外包一层。"""
    if name == "shell":
        return max(5.0, float(settings.shell_tool_timeout_sec))
    if name == "python_repl":
        return max(5.0, float(settings.python_repl_timeout_sec))
    if name in {"tavily_search", "duckduckgo_search"}:
        return max(3.0, float(settings.tool_search_timeout_sec))
    if name in {"read_file", "write_file", "list_directory"}:
        return max(2.0, float(settings.tool_file_timeout_sec))
    if name in {"rag_search", "rag_ingest"}:
        return max(5.0, float(settings.tool_default_timeout_sec))
    if name == "list_tools":
        return min(15.0, max(2.0, float(settings.tool_default_timeout_sec)))
    return max(5.0, float(settings.tool_default_timeout_sec))


async def execute_builtin(
    name: str,
    args: dict[str, Any],
    *,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """通过 LangChain ``BaseTool.ainvoke`` 执行内置工具，返回注册表约定的 ok/data/error 结构。

    Args:
        name: 工具名称
        args: 工具参数字典
        tool_context: 工具调用上下文（用户身份、会话 ID 等）
    """
    tool = builtin_lc_tools_by_name().get(name)
    if tool is None:
        return {"ok": False, "error": f"未实现的内置工具: {name}"}
    payload = dict(args) if args else {}
    settings = get_settings()
    timeout_sec = _tool_timeout_sec(name, settings)

    # 设置工具上下文
    old_context = get_current_tool_context()
    ctx = tool_context or old_context
    set_current_tool_context(ctx)

    try:
        # 参数校验（防止工具调用幻觉）
        validator = get_tool_args_validator()
        try:
            validated_payload = validator.validate(name, payload)
        except ToolValidationError as e:
            return {"ok": False, "error": str(e)}

        async with asyncio.timeout(timeout_sec):
            data = await _ainvoke_builtin(tool, validated_payload)
    except TimeoutError:
        return {
            "ok": False,
            "error": f"工具执行超时（{int(timeout_sec)}s）: {name}",
        }
    except ValidationError as e:
        return {"ok": False, "error": _tool_validation_error_message(e)}
    except Exception:
        logger.exception("builtin tool %s failed", name)
        return {"ok": False, "error": f"内置工具执行异常: {name}"}
    finally:
        set_current_tool_context(old_context)

    return {"ok": True, "data": data}


async def execute_builtin_with_context(
    name: str,
    args: dict[str, Any],
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """带上下文的工具执行（便捷方法）。

    自动创建 ToolContext 并在执行期间保持。
    """
    ctx = ToolContext(
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
    )
    return await execute_builtin(name, args, tool_context=ctx)


async def _ainvoke_builtin(tool: BaseTool, payload: dict[str, Any]) -> Any:
    """将计划步骤中的 args 与 LangChain StructuredTool 对齐（校验后 ainvoke）。

    如果工具支持 ToolContext，会自动注入。
    """
    schema_cls = getattr(tool, "args_schema", None)
    if isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
        validated = schema_cls.model_validate(payload)  # 校验
        canonical: dict[str, Any] = validated.model_dump(mode="json")  # 导出为字典
        return await tool.ainvoke(canonical)
    return await tool.ainvoke(payload)
