"""工具调用上下文：传递用户身份信息、会话信息等到工具执行层。

用于：
- 在工具执行时获取当前用户身份
- 传递会话 ID、任务 ID 等元信息
- 防止工具调用幻觉的参数校验
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """工具调用上下文。

    通过 ThreadLocal 或 contextvars 在异步环境中传递。
    """
    user_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文中的值。"""
        return getattr(self, key, default) or self.extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置上下文中的值。"""
        if hasattr(self, key):
            object.__setattr__(self, key, value)
        else:
            self.extra[key] = value

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "request_id": self.request_id,
            **self.extra,
        }


# ============================================================================
# Context Storage (ThreadLocal / contextvars)
# ============================================================================

try:
    from contextvars import ContextVar

    _tool_context_var: ContextVar[ToolContext | None] = ContextVar(
        "tool_context", default=None
    )

    def get_current_tool_context() -> ToolContext | None:
        """获取当前工具上下文。"""
        return _tool_context_var.get()

    def set_current_tool_context(ctx: ToolContext | None) -> None:
        """设置当前工具上下文。"""
        _tool_context_var.set(ctx)

    def with_tool_context(ctx: ToolContext | None):
        """上下文管理器：在指定工具上下文中执行代码。"""
        from contextvars import copy_context

        ctx_var = _tool_context_var
        token = ctx_var.set(ctx)
        try:
            yield
        finally:
            ctx_var.reset(token)

except ImportError:
    # Python 3.6 fallback (ThreadLocal)
    import threading

    _tool_context_local = threading.local()

    def get_current_tool_context() -> ToolContext | None:
        """获取当前工具上下文。"""
        return getattr(_tool_context_local, "tool_context", None)

    def set_current_tool_context(ctx: ToolContext | None) -> None:
        """设置当前工具上下文。"""
        _tool_context_local.tool_context = ctx

    def with_tool_context(ctx: ToolContext | None):
        """上下文管理器（ThreadLocal 版本）。"""
        old = get_current_tool_context()
        try:
            set_current_tool_context(ctx)
            yield
        finally:
            set_current_tool_context(old)
