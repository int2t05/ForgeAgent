"""单工具执行：落库 ``tool_call`` / ``tool_result``，失败时按次数重试。

由 ReAct 步内循环与同类执行路径共用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from langchain_community.tools.file_management.utils import (
    FileValidationError,
    get_validated_relative_path,
)

from app.core.circuit_breaker import CircuitOpenError, get_tool_circuit_breaker
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.tools.registry import tool_registry
from app.repositories import event_repository

logger = logging.getLogger(__name__)


def _args_for_display(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any] | None:
    """生成落库展示用 args 副本；文件类工具的路径字段在可校验时改为绝对路径。"""
    # 1. 仅文件工具需要路径展示增强
    if tool_name not in {"read_file", "write_file", "list_directory"}:
        return None
    settings = get_settings()
    root_path = settings.resolved_agent_workspace_path()
    out = dict(tool_args)
    try:
        # 2. read / write：替换 file_path
        if tool_name in ("read_file", "write_file"):
            fp = tool_args.get("file_path")
            if isinstance(fp, str) and fp.strip():
                p = get_validated_relative_path(root_path, fp)
                out["file_path"] = str(p.resolve())
            return out
        # 3. list_directory：替换 dir_path（缺省或「.」视为根）
        dp = tool_args.get("dir_path")
        if not isinstance(dp, str) or not dp.strip() or dp.strip() == ".":
            out["dir_path"] = str(root_path.resolve())
            return out
        p = get_validated_relative_path(root_path, dp)
        out["dir_path"] = str(p.resolve())
        return out
    except FileValidationError:
        # 4. 校验失败则保持原始入参，避免掩盖模型传入的非法路径
        return dict(tool_args)


def _tool_call_payload(
    step_id: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    max_tool_tries: int,
    react_thought: str | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "step_id": step_id,
        "tool": tool_name,
        "args": tool_args,
        "max_attempts": max_tool_tries,
    }
    if react_thought and str(react_thought).strip():
        row["thought"] = str(react_thought).strip()
    disp = _args_for_display(tool_name, tool_args)
    if disp is not None:
        row["args_for_display"] = disp
    return row


async def run_single_tool_with_retry(
    task_id: str,
    step_id: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    max_tool_tries: int,
    *,
    react_thought: str | None = None,
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    """带重试与熔断地执行命名工具，返回是否成功、末次执行结果及每次尝试列表。"""
    # 1. 落库 tool_call（步、参数、重试上限等）
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "tool",
                "tool_call",
                json.dumps(
                    _tool_call_payload(
                        step_id,
                        tool_name,
                        tool_args,
                        max_tool_tries,
                        react_thought,
                    ),
                    ensure_ascii=False,
                ),
            )

    # 2. 初始化尝试记录、末次结果、熔断器与退避参数
    attempt_rows: list[dict[str, Any]] = []
    final_ok = False
    last_exec: dict[str, Any] = {"ok": False, "data": None, "error": None}
    breaker = get_tool_circuit_breaker()
    settings = get_settings()
    base_delay = max(0.05, float(settings.tool_retry_base_delay_sec))
    max_delay = max(base_delay, float(settings.tool_retry_max_delay_sec))

    for attempt in range(1, max_tool_tries + 1):
        # 3. 熔断前置检查；开路则落库失败并结束循环
        try:
            breaker.before_call()
        except CircuitOpenError as e:
            last_exec = {"ok": False, "data": None, "error": str(e)}
            attempt_rows.append(
                {
                    "attempt": attempt,
                    "ok": False,
                    "data": None,
                    "error": str(e),
                }
            )
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_result",
                        json.dumps(
                            {
                                "step_id": step_id,
                                "tool": tool_name,
                                "attempt": attempt,
                                "max_attempts": max_tool_tries,
                                "ok": False,
                                "result": None,
                                "error": str(e),
                            },
                            ensure_ascii=False,
                        ),
                    )
            break

        # 4. 调用注册表执行工具
        exec_out = await tool_registry.execute(tool_name, tool_args)
        last_exec = {
            "ok": bool(exec_out.get("ok")),
            "data": exec_out.get("data"),
            "error": exec_out.get("error"),
        }
        ok = last_exec["ok"]
        # 5. 追加尝试快照并落库 tool_result
        attempt_rows.append(
            {
                "attempt": attempt,
                "ok": ok,
                "data": exec_out.get("data"),
                "error": exec_out.get("error"),
            }
        )
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "tool",
                    "tool_result",
                    json.dumps(
                        {
                            "step_id": step_id,
                            "tool": tool_name,
                            "attempt": attempt,
                            "max_attempts": max_tool_tries,
                            "ok": ok,
                            "result": exec_out.get("data"),
                            "error": exec_out.get("error"),
                        },
                        ensure_ascii=False,
                ),
            )
        # 6. 成功则标记熔断成功并结束重试循环
        if ok:
            breaker.record_success()
            final_ok = True
            break

        # 7. 失败：记录熔断失败；仍有次数则退避等待
        breaker.record_failure()
        if attempt < max_tool_tries:
            exp = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jitter = 0.5 + random.random() * 0.5
            wait = min(max_delay, exp * jitter)
            logger.warning(
                "工具失败将重试（%s/%s）：%s；等待 %.1fs",
                attempt,
                max_tool_tries,
                tool_name,
                wait,
            )
            await asyncio.sleep(wait)

    return final_ok, last_exec, attempt_rows
