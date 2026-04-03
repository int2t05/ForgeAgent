"""单工具执行：落库 ``tool_call`` / ``tool_result``，失败时按次数重试。

由 ReAct 步内循环与同类执行路径共用。
支持 Human-in-the-Loop 审批：敏感工具在执行前按设置模式拦截，等待人工确认。
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
from app.modules.execution.approval import (
    ExecutionMode,
    ApprovalManager,
    ApprovalStatus,
    approval_manager,
    is_sensitive_tool,
    _new_approval_id,
)
from app.modules.tools.registry import tool_registry
from app.repositories import event_repository

logger = logging.getLogger(__name__)


def _args_for_display(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any] | None:
    """生成落库展示用 args 副本；文件类工具的路径字段在可校验时改为绝对路径。"""
    if tool_name not in {"read_file", "write_file", "list_directory"}:
        return None
    settings = get_settings()
    root_path = settings.resolved_agent_workspace_path()
    out = dict(tool_args)
    try:
        if tool_name in ("read_file", "write_file"):
            fp = tool_args.get("file_path")
            if isinstance(fp, str) and fp.strip():
                p = get_validated_relative_path(root_path, fp)
                out["file_path"] = str(p.resolve())
            return out
        dp = tool_args.get("dir_path")
        if not isinstance(dp, str) or not dp.strip() or dp.strip() == ".":
            out["dir_path"] = str(root_path.resolve())
            return out
        p = get_validated_relative_path(root_path, dp)
        out["dir_path"] = str(p.resolve())
        return out
    except FileValidationError:
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
    _db: Any = None,
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    """带重试与熔断地执行命名工具，返回是否成功、末次执行结果及每次尝试列表。"""
    _owning_db = _db is None
    _session = _db or AsyncSessionLocal()

    async def _write_event(module: str, kind: str, payload: dict[str, Any] | str) -> None:
        payload_json = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        if _owning_db:
            async with _session.begin():
                await event_repository.append_event(
                    _session, task_id, module, kind, payload_json,
                )
        else:
            await event_repository.append_event(
                _session, task_id, module, kind, payload_json,
            )

    try:
        async with _session.begin():
            await event_repository.append_event(
                _session,
                task_id,
                "tool",
                "tool_call",
                json.dumps(
                    _tool_call_payload(
                        step_id, tool_name, tool_args, max_tool_tries, react_thought
                    ),
                    ensure_ascii=False,
                ),
            )

        attempt_rows: list[dict[str, Any]] = []
        final_ok = False
        last_exec: dict[str, Any] = {"ok": False, "data": None, "error": None}
        breaker = get_tool_circuit_breaker()
        settings = get_settings()
        base_delay = max(0.05, float(settings.tool_retry_base_delay_sec))
        max_delay = max(base_delay, float(settings.tool_retry_max_delay_sec))

        for attempt in range(1, max_tool_tries + 1):
            # 熔断前置检查；开路则落库失败并结束循环
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
                await _write_event(
                    "tool",
                    "tool_result",
                    {
                        "step_id": step_id,
                        "tool": tool_name,
                        "attempt": attempt,
                        "max_attempts": max_tool_tries,
                        "ok": False,
                        "result": None,
                        "error": str(e),
                    },
                )
                break

            # 调用注册表执行工具（前置 Human-in-the-Loop 审批检查）
            approved, approval_result = await _check_tool_approval(
                task_id, step_id, tool_name, tool_args, _write_event
            )
            if not approved:
                is_rejected = approval_result and "拒绝" in str(approval_result)
                last_exec = {
                    "ok": False,
                    "data": None,
                    "error": approval_result or "工具执行被拒绝",
                }
                attempt_rows.append(
                    {
                        "attempt": attempt,
                        "ok": False,
                        "data": None,
                        "error": last_exec["error"],
                    }
                )
                result_payload: dict[str, Any] = {
                    "step_id": step_id,
                    "tool": tool_name,
                    "attempt": attempt,
                    "max_attempts": max_tool_tries,
                    "ok": False,
                    "result": None,
                    "error": last_exec["error"],
                }
                if is_rejected:
                    result_payload["approval_rejected"] = True
                await _write_event(
                    "tool",
                    "tool_result",
                    result_payload,
                )
                if is_rejected:
                    await _write_event(
                        "execution",
                        "error",
                        {
                            "step_id": step_id,
                            "tool": tool_name,
                            "error_type": "approval_rejected",
                            "message": str(approval_result),
                        },
                    )
                break

            exec_out = await tool_registry.execute(tool_name, tool_args)
            last_exec = {
                "ok": bool(exec_out.get("ok")),
                "data": exec_out.get("data"),
                "error": exec_out.get("error"),
            }
            ok = last_exec["ok"]
            attempt_rows.append(
                {
                    "attempt": attempt,
                    "ok": ok,
                    "data": exec_out.get("data"),
                    "error": exec_out.get("error"),
                }
            )
            await _write_event(
                "tool",
                "tool_result",
                {
                    "step_id": step_id,
                    "tool": tool_name,
                    "attempt": attempt,
                    "max_attempts": max_tool_tries,
                    "ok": ok,
                    "result": exec_out.get("data"),
                    "error": exec_out.get("error"),
                },
            )
            if ok:
                breaker.record_success()
                final_ok = True
                break

            # 失败：记录熔断失败；仍有次数则退避等待
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
    finally:
        if _owning_db:
            try:
                await _session.close()
            except Exception:
                pass


async def _check_tool_approval(
    task_id: str,
    step_id: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    write_event: Any,
) -> tuple[bool, str | None]:
    """根据当前执行模式决定敏感工具是否需要人工审批。

    返回 (是否允许执行, 拒绝原因/None)。
    auto 模式直接放行；confirm 模式每次拦截；learn 模式检查白名单。
    """
    # 1. 非敏感工具直接放行
    if not is_sensitive_tool(tool_name):
        logger.debug("工具非敏感，跳过审批: task=%s tool=%s", task_id, tool_name)
        return True, None

    # 2. 读取当前执行模式（从 settings_kv）
    try:
        mode = await _get_execution_mode()
    except Exception as e:
        logger.error("读取执行模式失败（默认 auto 放行）: task=%s error=%s", task_id, e)
        return True, None

    mode_str = mode.value if isinstance(mode, ExecutionMode) else (mode or "auto")
    logger.info(
        "审批检查: task=%s tool=%s mode=%s sensitive=True",
        task_id, tool_name, mode_str,
    )

    if mode == ExecutionMode.AUTO:
        logger.info("auto 模式直接放行: task=%s tool=%s", task_id, tool_name)
        return True, None

    # 3. learn 模式：检查已批准工具列表
    if mode == ExecutionMode.LEARN:
        try:
            approved_tools = await _get_approved_tool_patterns()
            if _is_tool_approved(tool_name, approved_tools):
                logger.info("learn 白名单命中，放行: task=%s tool=%s", task_id, tool_name)
                return True, None
        except Exception as e:
            logger.warning("learn 白名单查询失败（默认拦截）: task=%s error=%s", task_id, e)

    # 4. 需要审批：预创建请求获取 ID → 写 required 事件 → 等待用户响应 → 写 result 事件
    logger.info(
        "敏感工具等待人工审批: task=%s tool=%s mode=%s",
        task_id, tool_name, mode_str,
    )

    try:
        req_id = _new_approval_id()
        req = approval_manager._create_request(task_id, tool_name, tool_args, req_id)

        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "tool",
                    "tool_approval_required",
                    json.dumps({
                        "step_id": step_id,
                        "tool": tool_name,
                        "args": tool_args,
                        "mode": mode_str,
                        "approval_id": req.id,
                    }, ensure_ascii=False),
                )
        logger.info("审批事件已写入，等待用户响应: task=%s approval_id=%s", task_id, req_id)

        await approval_manager._wait_for_result(req)
        logger.info("用户已响应审批: task=%s approval_id=%s status=%s", task_id, req.id, req.status.value)

        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "tool",
                    "tool_approval_result",
                    json.dumps({
                        "step_id": step_id,
                        "tool": tool_name,
                        "approval_id": req.id,
                        "status": req.status.value,
                    }, ensure_ascii=False),
                )
    except Exception as e:
        logger.exception("审批流程异常（默认拒绝）: task=%s tool=%s error=%s", task_id, tool_name, e)
        return False, f"审批流程异常: {e}"

    if req.status == ApprovalStatus.APPROVED:
        if mode == ExecutionMode.LEARN:
            try:
                await _record_approved_tool(tool_name)
            except Exception as e:
                logger.warning("记录已批准工具失败: tool=%s error=%s", tool_name, e)
        return True, None

    if req.status == ApprovalStatus.REJECTED:
        return False, f"用户拒绝了工具执行: {tool_name}"

    if req.status in (ApprovalStatus.TIMEOUT, ApprovalStatus.CANCELLED):
        return False, f"工具审批{req.status.value}: {tool_name}"

    return False, f"未知审批状态: {req.status.value}"


async def _get_execution_mode() -> str | None:
    """从 settings_kv 读取 execution_mode；缺失或非法值默认 auto。"""
    from app.repositories.settings_repository import get_value
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = await get_value(db, "execution_mode")
    if row is None:
        return None
    try:
        import json
        parsed = json.loads(row.value_json)
        if isinstance(parsed, str) and parsed in (m.value for m in ExecutionMode):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return None


async def _get_approved_tool_patterns() -> list[str]:
    """从 settings_kv 读取 learn 模式的已批准工具名列表。"""
    from app.repositories.settings_repository import get_value
    from app.core.database import AsyncSessionLocal
    import json

    async with AsyncSessionLocal() as db:
        row = await get_value(db, "approved_tool_patterns")
    if row is None:
        return []
    try:
        parsed = json.loads(row.value_json)
        if isinstance(parsed, list):
            return [str(t) for t in parsed if isinstance(t, str)]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _is_tool_approved(tool_name: str, patterns: list[str]) -> bool:
    """检查工具名是否匹配已批准模式（精确匹配）。"""
    return tool_name in patterns


async def _record_approved_tool(tool_name: str) -> None:
    """将新批准的工具名追加到 approved_tool_patterns。"""
    from app.repositories.settings_repository import upsert_value
    from app.core.database import AsyncSessionLocal
    import json

    existing = await _get_approved_tool_patterns()
    if tool_name in existing:
        return
    existing.append(tool_name)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await upsert_value(
                db,
                "approved_tool_patterns",
                json.dumps(existing, ensure_ascii=False),
            )
