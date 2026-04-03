"""Human-in-the-Loop 工具审批管理器：敏感工具执行前中断，等待人工确认/拒绝。

三种执行模式（存于 settings_kv.execution_mode）：
- auto:    全部自动执行，不拦截
- confirm: 每次敏感工具均弹窗等待人工确认
- learn:   首次确认后记录工具名，后续同名工具自动放行

敏感工具集合（硬编码，覆盖内置与 MCP 写操作）：
- python_repl, shell, write_file 及含 write 的 MCP 工具
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """工具执行策略。"""

    AUTO = "auto"
    CONFIRM = "confirm"
    LEARN = "learn"


class ApprovalStatus(str, Enum):
    """单条审批记录的状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


SENSITIVE_TOOL_NAMES: frozenset[str] = frozenset({
    "python_repl",
    "shell",
    "write_file",
})


def is_sensitive_tool(tool_name: str) -> bool:
    """判断工具名是否属于需人工审批的敏感工具集合。"""
    if tool_name in SENSITIVE_TOOL_NAMES:
        return True
    return tool_name.lower().startswith("write") or "_write" in tool_name.lower()


@dataclass
class ApprovalRequest:
    """单条待审批请求（进程内存）。"""

    id: str
    task_id: str
    tool_name: str
    tool_args: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.monotonic)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    timeout_sec: float = 300.0


class ApprovalManager:
    """进程内审批请求生命周期管理。

    线程安全要点：所有公开方法仅在 asyncio 事件循环线程调用（Agent 后台任务 + FastAPI 路由），
    因此无需额外锁；字典读写由单线程 event loop 串行化。
    """

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}

    def _create_request(
        self,
        task_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        req_id: str,
        *,
        timeout_sec: float = 300.0,
    ) -> ApprovalRequest:
        """创建审批请求（不阻塞），返回 request 对象供后续等待。"""
        req = ApprovalRequest(
            id=req_id,
            task_id=task_id,
            tool_name=tool_name,
            tool_args=tool_args,
            timeout_sec=timeout_sec,
        )
        self._pending[req_id] = req
        logger.info(
            "审批请求创建: id=%s task=%s tool=%s (等待人工确认)",
            req_id, task_id, tool_name,
        )
        return req

    async def _wait_for_result(self, req: ApprovalRequest) -> None:
        """阻塞等待用户决策；超时时自动设为 TIMEOUT 并清理。"""
        try:
            await asyncio.wait_for(req.event.wait(), timeout=req.timeout_sec)
        except TimeoutError:
            req.status = ApprovalStatus.TIMEOUT
            logger.warning(
                "审批超时: id=%s task=%s tool=%s (%.0fs)",
                req.id, req.task_id, req.tool_name, req.timeout_sec,
            )
        finally:
            self._pending.pop(req.id, None)

    async def request_approval(
        self,
        task_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        timeout_sec: float = 300.0,
    ) -> ApprovalRequest:
        """创建审批请求并阻塞等待用户决策；超时或任务取消时返回对应状态。"""
        req_id = _new_approval_id()
        req = self._create_request(task_id, tool_name, tool_args, req_id, timeout_sec=timeout_sec)
        await self._wait_for_result(req)
        return req

    def approve(self, approval_id: str) -> bool:
        """人工批准：唤醒等待中的协程。"""
        req = self._pending.get(approval_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False
        req.status = ApprovalStatus.APPROVED
        req.event.set()
        logger.info("审批通过: id=%s tool=%s", approval_id, req.tool_name)
        return True

    def reject(self, approval_id: str) -> bool:
        """人工拒绝：唤醒等待中的协程（以错误结果返回给 Agent）。"""
        req = self._pending.get(approval_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False
        req.status = ApprovalStatus.REJECTED
        req.event.set()
        logger.info("审批拒绝: id=%s tool=%s", approval_id, req.tool_name)
        return True

    def cancel_for_task(self, task_id: str) -> int:
        """任务取消时释放该任务下所有 pending 审批；返回释放数量。"""
        count = 0
        for rid, req in list(self._pending.items()):
            if req.task_id == task_id and req.status == ApprovalStatus.PENDING:
                req.status = ApprovalStatus.CANCELLED
                req.event.set()
                count += 1
        if count:
            logger.info("任务 %s 取消，释放 %d 条待审批请求", task_id, count)
        return count

    def get_pending(self, task_id: str | None = None) -> list[ApprovalRequest]:
        """查询当前 pending 的审批列表；可按 task_id 过滤。"""
        items = [
            r for r in self._pending.values() if r.status == ApprovalStatus.PENDING
        ]
        if task_id is not None:
            items = [r for r in items if r.task_id == task_id]
        return items

    def get_pending_by_id(self, approval_id: str) -> ApprovalRequest | None:
        """按 ID 查询单条审批请求（含已完成但未清理的）。"""
        return self._pending.get(approval_id)


approval_manager = ApprovalManager()


def _new_approval_id() -> str:
    return f"apr-{uuid.uuid4().hex[:12]}"
