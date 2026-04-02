"""MCP Client 管理器：维护与真实 MCP Server 的长连接会话（stdio / SSE / HTTP）。

每个 enabled MCP Server 对应一个 ``_McpConnection``，在 ``McpClientManager.connect``
时建立会话，可反复用于 ``list_tools`` / ``call_tool``；``close`` 时优雅释放全部资源。

线程安全通过 ``asyncio.Lock`` 保证；非线程安全的 anyio / MCP SDK 调用均在同一事件循环内执行。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SEC = 30.0
_CALL_TOOL_TIMEOUT_SEC = 120.0

_REAL_TRANSPORTS = frozenset({"stdio", "sse", "http"})


def normalize_mcp_transport(raw: Any) -> str:
    """将配置里的 transport 规范为小写形式。"""
    t = str(raw or "").lower().replace("_", "-")
    if t in {"streamable-http", "streamablehttp", "http"}:
        return "http"
    return t


def _normalize_headers(raw: Any) -> dict[str, str] | None:
    """供 HTTP 客户端使用：键值均为 str，空则返回 None。"""
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        out[key] = v if isinstance(v, str) else str(v)
    return out or None


def _resolve_stdio_executable(command: str) -> str | None:
    """在 PATH 中解析可执行文件；Windows 上补试 ``.cmd`` / ``.exe``。"""
    cmd = command.strip()
    if not cmd:
        return None
    found = shutil.which(cmd)
    if found:
        return found
    if sys.platform == "win32":
        for ext in (".cmd", ".exe", ".bat"):
            found = shutil.which(f"{cmd}{ext}")
            if found:
                return found
    return None


def _mcp_connect_fingerprint(cfg: dict[str, Any]) -> str:
    """连接参数指纹：变更 url / headers / command / args / env 时需重连。"""
    args = cfg.get("args")
    args_list: list[str]
    if isinstance(args, list):
        args_list = [str(a) for a in args]
    else:
        args_list = []
    env = cfg.get("env")
    env_map: dict[str, str] = {}
    if isinstance(env, dict):
        for ek, ev in env.items():
            env_map[str(ek)] = str(ev)
    headers = _normalize_headers(cfg.get("headers")) or {}
    payload = {
        "t": normalize_mcp_transport(cfg.get("transport")),
        "cmd": str(cfg.get("command") or "").strip(),
        "args": args_list,
        "url": str(cfg.get("url") or "").strip(),
        "headers": {k: headers[k] for k in sorted(headers)},
        "env": {k: env_map[k] for k in sorted(env_map)},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class McpToolMeta:
    """从真实 MCP Server 拉取到的工具元数据。"""

    name: str
    description: str
    input_schema: dict[str, Any] | None = None


@dataclass
class _McpConnection:
    """一个 MCP Server 的连接上下文（含 async context manager 栈）。"""

    server_name: str
    transport: str = ""
    session: ClientSession | None = None
    _exit_stack: contextlib.AsyncExitStack = field(default_factory=contextlib.AsyncExitStack)

    async def close(self) -> None:
        try:
            await self._exit_stack.aclose()
        except RuntimeError as exc:
            # anyio 的 cancel scope 需要在进入它的同一 task 中退出；
            # 某些 streamable HTTP 版本在跨 task 关闭时会触发该异常。
            if "Attempted to exit cancel scope in a different task" in str(exc):
                logger.debug(
                    "关闭 MCP 连接出现已知跨 task cancel-scope 异常（忽略）: %s",
                    self.server_name,
                )
            else:
                logger.warning("关闭 MCP 连接失败: %s", self.server_name, exc_info=True)
        except Exception:
            logger.warning("关闭 MCP 连接失败: %s", self.server_name, exc_info=True)
        finally:
            self.session = None


def _friendly_connect_error(name: str, transport: str, exc: BaseException) -> str:
    """从底层异常中提取面向用户的一行诊断信息。"""
    msg = str(exc)
    cls = type(exc).__name__

    if isinstance(exc, FileNotFoundError):
        return (
            f"[{name}] stdio command 不存在或不在 PATH 中。"
            "请确认 command 拼写正确且已安装（如 npx、node、uvx 等）。"
        )

    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            inner = _friendly_connect_error(name, transport, sub)
            if inner != msg:
                return inner
        return f"[{name}] 连接失败（ExceptionGroup）: {msg}"

    if "401" in msg or "Unauthorized" in msg:
        return (
            f"[{name}] MCP 端点返回 401 Unauthorized。"
            "请在 MCP 配置中添加 headers（如 Authorization）或检查认证信息。"
        )
    if "403" in msg or "Forbidden" in msg:
        return f"[{name}] MCP 端点返回 403 Forbidden，权限不足。"
    if "404" in msg or "Not Found" in msg:
        return f"[{name}] MCP 端点返回 404，URL 可能错误: 请检查配置的 url。"
    if "405" in msg or "Method Not Allowed" in msg:
        return (
            f"[{name}] HTTP 405 Method Not Allowed。"
            "该端点可能是 streamable HTTP，而当前 transport 配置不匹配；"
            "请尝试将 transport 设为 http，或核对服务端支持的传输类型。"
        )
    if "Connection refused" in msg:
        return f"[{name}] 连接被拒绝——目标 Server 可能未启动。"
    if "Connection closed" in msg or "ConnectionReset" in cls:
        return (
            f"[{name}] Server 在握手阶段关闭了连接。"
            "常见原因：command/args 不正确导致进程立即退出，或 Server 版本不兼容。"
        )

    if isinstance(exc, TimeoutError):
        return f"[{name}] 连接超时（{_CONNECT_TIMEOUT_SEC}s），Server 可能未响应。"

    return f"[{name}] {cls}: {msg}"


class McpClientManager:
    """进程级 MCP 连接池：按 server 名称维护会话，支持 list / call。"""

    def __init__(self) -> None:
        self._conns: dict[str, _McpConnection] = {}
        self._cfg_fingerprint: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def connect(self, server_cfgs: list[dict[str, Any]]) -> None:
        """根据 settings.mcp 列表（仅非 mock、已启用条目）建立或刷新连接。

        已存在且配置未变的连接保留；不再出现的断开。
        """
        async with self._lock:
            desired: dict[str, dict[str, Any]] = {}
            for cfg in server_cfgs:
                if not isinstance(cfg, dict):
                    continue
                if cfg.get("enabled") is False:
                    continue
                if normalize_mcp_transport(cfg.get("transport")) not in _REAL_TRANSPORTS:
                    continue
                name = str(cfg.get("name") or "mcp").strip() or "mcp"
                desired[name] = cfg

            # 1. 关闭已移除 / disabled 的连接
            removed = [k for k in self._conns if k not in desired]
            for k in removed:
                conn = self._conns.pop(k)
                await conn.close()
                self._cfg_fingerprint.pop(k, None)

            # 2. 配置变更的已连接项：先断开再重建（否则会一直沿用无 headers 的旧会话）
            for name, cfg in desired.items():
                if name not in self._conns:
                    continue
                fp = _mcp_connect_fingerprint(cfg)
                if self._cfg_fingerprint.get(name) == fp:
                    continue
                conn = self._conns.pop(name)
                await conn.close()
                self._cfg_fingerprint.pop(name, None)

            # 3. 建立新连接或重连失败的槽位
            for name, cfg in desired.items():
                if name in self._conns and self._conns[name].session is not None:
                    continue
                transport = normalize_mcp_transport(cfg.get("transport"))
                fp = _mcp_connect_fingerprint(cfg)
                try:
                    conn = await asyncio.wait_for(
                        self._open_connection(name, cfg),
                        timeout=_CONNECT_TIMEOUT_SEC,
                    )
                    self._conns[name] = conn
                    self._cfg_fingerprint[name] = fp
                    logger.info("MCP 连接已建立: %s (%s)", name, transport)
                except BaseException as exc:
                    self._cfg_fingerprint.pop(name, None)
                    friendly = _friendly_connect_error(name, transport, exc)
                    logger.error("MCP 连接失败: %s", friendly)
                    logger.debug("MCP 连接失败详细堆栈: %s", name, exc_info=True)

    async def close_all(self) -> None:
        """关闭所有 MCP 连接。"""
        async with self._lock:
            for conn in self._conns.values():
                await conn.close()
            self._conns.clear()
            self._cfg_fingerprint.clear()

    # ------------------------------------------------------------------
    # 工具列表
    # ------------------------------------------------------------------

    async def list_tools(self, server_name: str) -> list[McpToolMeta]:
        """拉取指定 server 的工具列表。"""
        conn = self._conns.get(server_name)
        if conn is None or conn.session is None:
            return []
        try:
            result = await conn.session.list_tools()
            return [
                McpToolMeta(
                    name=t.name,
                    description=t.description or "",
                    input_schema=t.inputSchema if hasattr(t, "inputSchema") else None,
                )
                for t in result.tools
            ]
        except Exception as exc:
            # 连接底层流已关闭时，移除失效连接，避免后续请求持续报同类错误。
            dead_conn = (
                "ClosedResourceError" in type(exc).__name__
                or "Attempted to exit cancel scope in a different task" in str(exc)
            )
            if dead_conn:
                logger.warning("MCP 连接已失效，移除并等待下次自动重连: %s", server_name)
                async with self._lock:
                    conn = self._conns.pop(server_name, None)
                    self._cfg_fingerprint.pop(server_name, None)
                    if conn is not None:
                        conn.session = None
            else:
                logger.error("MCP list_tools 失败: %s", server_name, exc_info=True)
            return []

    async def list_all_tools(self) -> dict[str, list[McpToolMeta]]:
        """拉取所有已连接 server 的工具列表。"""
        out: dict[str, list[McpToolMeta]] = {}
        for name in list(self._conns):
            out[name] = await self.list_tools(name)
        return out

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """调用指定 server 上的工具，返回统一 ok/data/error 结构。"""
        conn = self._conns.get(server_name)
        if conn is None or conn.session is None:
            return {"ok": False, "error": f"MCP Server 未连接: {server_name}"}
        try:
            result = await asyncio.wait_for(
                conn.session.call_tool(tool_name, arguments=arguments or {}),
                timeout=_CALL_TOOL_TIMEOUT_SEC,
            )
            text_parts: list[str] = []
            for block in result.content:
                if isinstance(block, types.TextContent):
                    text_parts.append(block.text)
                elif isinstance(block, types.EmbeddedResource):
                    text_parts.append(f"[embedded resource: {block.resource}]")
                else:
                    text_parts.append(str(block))
            data = "\n".join(text_parts) if text_parts else "(empty)"
            if result.isError:
                return {"ok": False, "error": data}
            return {"ok": True, "data": data}
        except TimeoutError:
            return {"ok": False, "error": f"MCP call_tool 超时（{_CALL_TOOL_TIMEOUT_SEC}s）: {tool_name}@{server_name}"}
        except Exception as exc:
            logger.error("MCP call_tool 异常: %s/%s", server_name, tool_name, exc_info=True)
            return {"ok": False, "error": f"MCP 工具执行异常: {exc}"}

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def connected_server_names(self) -> list[str]:
        return [k for k, v in self._conns.items() if v.session is not None]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _open_connection(self, name: str, cfg: dict[str, Any]) -> _McpConnection:
        """建立单个 MCP Server 连接并完成 initialize 握手。"""
        transport = normalize_mcp_transport(cfg.get("transport"))
        conn = _McpConnection(server_name=name, transport=transport)
        try:
            if transport == "stdio":
                await self._open_stdio(conn, cfg)
            elif transport == "sse":
                await self._open_sse(conn, cfg)
            elif transport == "http":
                await self._open_streamable_http(conn, cfg)
            else:
                raise ValueError(f"不支持的 MCP transport: {transport}")
            if conn.session is not None:
                await conn.session.initialize()
            return conn
        except BaseException:
            await conn.close()
            raise

    async def _open_stdio(self, conn: _McpConnection, cfg: dict[str, Any]) -> None:
        command = str(cfg.get("command") or "").strip()
        if not command:
            raise ValueError(f"stdio MCP Server 缺少 command: {conn.server_name}")

        resolved = _resolve_stdio_executable(command)
        if resolved is None:
            raise FileNotFoundError(
                f"command '{command}' 未找到。"
                f"请确认已安装，且运行后端的进程 PATH 与终端一致（Windows 可写完整路径；"
                f"Server: {conn.server_name}）。"
            )

        raw_args = cfg.get("args")
        args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
        raw_env = cfg.get("env")
        env: dict[str, str] | None = None
        if isinstance(raw_env, dict):
            env = {str(k): v if isinstance(v, str) else str(v) for k, v in raw_env.items()}

        params = StdioServerParameters(command=resolved, args=args, env=env)
        read_stream, write_stream = await conn._exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await conn._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        conn.session = session

    async def _open_sse(self, conn: _McpConnection, cfg: dict[str, Any]) -> None:
        url = str(cfg.get("url") or "").strip()
        if not url:
            raise ValueError(f"SSE MCP Server 缺少 url: {conn.server_name}")
        headers = _normalize_headers(cfg.get("headers"))

        read_stream, write_stream = await conn._exit_stack.enter_async_context(
            sse_client(url, headers=headers)
        )
        session = await conn._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        conn.session = session

    async def _open_streamable_http(self, conn: _McpConnection, cfg: dict[str, Any]) -> None:
        """建立 streamable HTTP 连接，并兼容不同 mcp 版本的参数签名。"""
        url = str(cfg.get("url") or "").strip()
        if not url:
            raise ValueError(f"HTTP MCP Server 缺少 url: {conn.server_name}")
        headers = _normalize_headers(cfg.get("headers"))
        sig_params = inspect.signature(streamable_http_client).parameters
        supports_headers = "headers" in sig_params
        # 1. 新版 mcp：streamable_http_client 支持 headers。
        # 2. 中间版本：通过 httpx_client_factory 注入默认请求头。
        # 3. 旧版：通过 http_client 注入默认请求头。
        if supports_headers:
            ctx = streamable_http_client(url, headers=headers)
        elif "httpx_client_factory" in sig_params:
            if headers:

                def _factory() -> httpx.AsyncClient:
                    return httpx.AsyncClient(headers=headers)

                ctx = streamable_http_client(url, httpx_client_factory=_factory)
            else:
                ctx = streamable_http_client(url)
        elif "http_client" in sig_params:
            if headers:
                http_client = await conn._exit_stack.enter_async_context(
                    httpx.AsyncClient(headers=headers)
                )
                ctx = streamable_http_client(url, http_client=http_client)
            else:
                ctx = streamable_http_client(url)
        else:
            if headers:
                logger.warning(
                    "当前 mcp 版本的 streamable_http_client 无法注入请求头，"
                    "将忽略 headers（server=%s）",
                    conn.server_name,
                )
            ctx = streamable_http_client(url)

        read_stream, write_stream, _ = await conn._exit_stack.enter_async_context(ctx)
        session = await conn._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        conn.session = session


# 进程级单例
mcp_client_manager = McpClientManager()
