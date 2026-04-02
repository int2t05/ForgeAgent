"""内置工具的 LangChain 封装：以官方集成包提供的工具为主，避免重复实现检索与百科能力。

对齐 LangChain 文档（Python）：

- DuckDuckGo：https://docs.langchain.com/oss/python/integrations/providers/duckduckgo_search
- Tavily：https://docs.langchain.com/oss/python/integrations/tools/tavily_search（推荐 ``langchain-tavily``）
- 文件读写列举：``read_file`` / ``write_file`` 为工作区封装（支持按行局部读写），``list_directory`` 用 ``langchain_community.tools.file_management``（根目录由 ``Settings.resolved_agent_workspace_path`` 约束）
- Python 交互执行：``langchain_experimental.tools.PythonREPLTool``（可经 ``AGENT_ENABLE_PYTHON_REPL`` 关闭）
- Shell：自建 ``StructuredTool``（与文件工具共享工作区根 + 子进程超时；Windows 默认 ``cmd.exe /c``，Unix 常见 ``/bin/sh``）

另保留 ``list_tools``：查询本进程统一工具注册表元数据，属产品内建能力，无社区替代品。

执行路径仍经 ``BaseTool.ainvoke``（见 ``builtin_executor``），与 LangGraph / Agent 工具调用约定一致。
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool, tool
from pydantic import BaseModel, Field, model_validator

from app.core.config import Settings, get_settings
from app.modules.tools.forge_file_tools import (
    build_forge_read_file_tool,
    build_forge_write_file_tool,
)
from app.schemas.tools import ToolItem

logger = logging.getLogger(__name__)

# shell 工具单次脚本长度上限（字符），防止异常大 payload
_MAX_SHELL_SCRIPT_CHARS = 262_144

# Windows：在 cmd 会话开头切到 UTF-8 代码页，减轻中文与路径乱码（失败时仍执行后续命令）
_WIN_CMD_UTF8 = "chcp 65001 >nul & "


def _strip_powershell_clixml(text: str) -> str:
    """去掉 PowerShell 写入的 CLIXML 进度/序列化块，避免淹没真实输出。"""
    if not text or ("CLIXML" not in text and "<Objs" not in text):
        return text
    cur = text
    pat_header = re.compile(r"(?s)#<\s*CLIXML\s*\r?\n.*?</Objs>\s*")
    pat_ns = re.compile(
        r'(?s)<Objs\b[^>]*xmlns="http://schemas\.microsoft\.com/powershell/2004/04"[^>]*>'
        r".*?</Objs>\s*"
    )
    prev = None
    while prev != cur:
        prev = cur
        cur = pat_header.sub("", cur)
        cur = pat_ns.sub("", cur)
    return cur.strip()


def _windows_shell_unsupported(script: str) -> str | None:
    """在 Windows（cmd）上拦截典型 Bash/Unix 习惯用法，返回 cmd 等价说明。"""
    s = script.strip()
    if not s:
        return None
    low = s.lower()

    if re.search(r"(?:^|[;&|]|\n)\s*xargs\b", low):
        return (
            "Error: 当前由 Windows **cmd.exe** 执行，没有 xargs，也不要写 `find … | xargs …`。\n"
            "递归在文件内容里搜索（类似 grep -r）可用：\n"
            "  findstr /S /M /I \"关键词\" *.py\n"
            "只看某目录树下路径可配合通配：\n"
            "  dir /S /B backend\\app\\*.py\n"
            "（更复杂场景可用 python -c 或仓库内文件工具。）"
        )

    if re.search(r"\bfind\s+.+\s+-type\b", low):
        return (
            "Error: `find -type` 是 Unix find 语法，cmd 不支持。\n"
            "列举某目录下全部文件路径（示例）：\n"
            "  dir /S /B <目录>\\*.*\n"
            "只要某种扩展名：\n"
            "  dir /S /B backend\\app\\*.py"
        )

    if re.search(r"\bfind\s+.+\s+-name\b", low):
        return (
            "Error: `find -name` 是 Unix 语法，请改用 cmd 通配符：\n"
            "  dir /S /B <路径\\*.py>\n"
            "示例：dir /S /B backend\\app\\*.py"
        )

    if "/dev/null" in low or re.search(r"2>\s*/dev/null", low):
        return (
            "Error: `/dev/null` 与 `2>/dev/null` 是 Unix 重定向；在 **cmd** 里丢弃标准错误请用：\n"
            "  2>nul\n"
            "示例：some_command 2>nul"
        )

    return None


def _wall_timeout_sec(
    raw: float, *, default: float = 120.0, floor: float | None = None
) -> float:
    v = default if raw <= 0 else raw
    if floor is not None:
        v = max(floor, v)
    return v


def _subprocess_shell_sync(script: str, cwd: str, timeout_sec: float) -> str:
    """Windows 专用：经 cmd.exe /c 执行（非交互、合并 stderr 到 stdout）。"""
    cmd_line = _WIN_CMD_UTF8 + script.lstrip()
    argv = ["cmd.exe", "/d", "/s", "/c", cmd_line]
    run_kw: dict[str, Any] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "timeout": timeout_sec,
        "env": os.environ.copy(),
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        run_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(argv, **run_kw)
    except subprocess.TimeoutExpired:
        return (
            f"Error: shell 已超时（>{int(timeout_sec)}s）并已终止子进程。"
            "若脚本在等待输入或死循环，请改为非交互或调大 SHELL_TOOL_TIMEOUT_SEC。"
            f" 当前工作目录: {cwd}"
        )
    raw = completed.stdout or b""
    text = raw.decode(errors="replace").strip()
    text = _strip_powershell_clixml(text)
    code = completed.returncode if completed.returncode is not None else -1
    if code != 0:
        prefix = f"exit {code}"
        return f"{prefix}\n{text}" if text else prefix
    return text or "(no output)"


async def _subprocess_shell_output(
    script: str, *, cwd: str, timeout_sec: float
) -> str:
    # Windows 上若为 SelectorEventLoop，asyncio.create_subprocess_shell 会抛 NotImplementedError；
    # 亦避免依赖进程须在启动时强制 WindowsProactorEventLoopPolicy。
    if platform.system() == "Windows":
        return await asyncio.to_thread(
            _subprocess_shell_sync, script, cwd, timeout_sec
        )
    proc = await asyncio.create_subprocess_shell(
        script,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=os.environ.copy(),
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_sec,
        )
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        return (
            f"Error: shell 已超时（>{int(timeout_sec)}s）并已终止子进程。"
            "若脚本在等待输入或死循环，请改为非交互或调大 SHELL_TOOL_TIMEOUT_SEC。"
            f" 当前工作目录: {cwd}"
        )
    text = (out or b"").decode(errors="replace").strip()
    code = proc.returncode if proc.returncode is not None else -1
    if code != 0:
        prefix = f"exit {code}"
        return f"{prefix}\n{text}" if text else prefix
    return text or "(no output)"


class ListToolsInput(BaseModel):
    """list_tools 入参。"""

    names: list[str] | None = Field(
        default=None,
        description=(
            "要查询的工具名称列表；省略或空列表表示返回当前注册表中的全部工具 "
            "（内置 + 已配置的 MCP / Skill 元数据）。"
        ),
    )


@tool("list_tools", args_schema=ListToolsInput)
async def list_tools_tool(names: list[str] | None = None) -> dict[str, Any]:
    """返回当前进程内工具注册表快照中的工具元数据（名称、说明、来源、入参 schema）；可按名称筛选。"""
    # 1. 延迟导入 ToolRegistry，避免与 builtin 循环依赖
    from app.modules.tools.registry import tool_registry

    snapshot = tool_registry.list_tools_public().tools
    if names is None or len(names) == 0:
        selected = snapshot
        unknown: list[str] = []
    else:
        known = {t.name for t in snapshot}
        want = list(dict.fromkeys(names))
        unknown = [n for n in want if n not in known]
        want_set = set(want)
        selected = [t for t in snapshot if t.name in want_set]
    return {
        "tools": [t.model_dump(mode="json") for t in selected],
        "count": len(selected),
        "unknown_names": unknown,
    }


def _duckduckgo_search_tool() -> BaseTool:
    """DuckDuckGo 网页检索（需已安装 ``ddgs``，见官方集成页）。"""
    from langchain_community.tools import DuckDuckGoSearchRun

    return DuckDuckGoSearchRun()


def _tavily_search_tool() -> BaseTool | None:
    """Tavily 搜索；仅当配置了 ``TAVILY_API_KEY``（或 Settings.tavily_api_key）时启用。"""
    settings = get_settings()
    key = (settings.tavily_api_key or "").strip()
    if not key:
        return None
    try:
        from langchain_tavily import TavilySearch
    except ImportError:
        logger.warning(
            "已配置 TAVILY_API_KEY 但未安装 langchain-tavily，跳过 tavily_search 内置工具"
        )
        return None
    return TavilySearch(
        max_results=5,
        topic="general",
        tavily_api_key=key,
    )


def _build_community_builtin_tools() -> tuple[BaseTool, ...]:
    """组装官方社区工具列表；顺序影响设置页展示（检索类靠前）。"""
    items: list[BaseTool] = []
    tavily = _tavily_search_tool()
    if tavily is not None:
        items.append(tavily)
    else:
        items.append(_duckduckgo_search_tool())
    return tuple(items)


def _workspace_root_str(settings: Settings) -> str:
    """文件工具所需的根目录字符串（绝对路径）。"""
    root: Path = settings.resolved_agent_workspace_path()
    return str(root)


def _build_file_management_tools() -> tuple[BaseTool, ...]:
    """在配置的工作区根下提供 read / write / list_directory。"""
    from langchain_community.tools.file_management import ListDirectoryTool

    settings = get_settings()
    root = _workspace_root_str(settings)
    return (
        build_forge_read_file_tool(root),
        build_forge_write_file_tool(root),
        ListDirectoryTool(root_dir=root),
    )


class PythonREPLInput(BaseModel):
    """``python_repl`` 入参：LangChain 原版字段为 ``query``，模型常误写为 ``code``。"""

    query: str | None = Field(
        default=None,
        description="要执行的 Python 源码（与 code 二选一）",
    )
    code: str | None = Field(
        default=None,
        description="与 query 完全等价，任选其一传入即可",
    )

    @model_validator(mode="after")
    def _at_least_one(self) -> PythonREPLInput:
        if not (self.query or "").strip() and not (self.code or "").strip():
            raise ValueError("必须提供非空的 query 或 code 之一")
        return self

    def resolved_source(self) -> str:
        c = (self.code or "").strip()
        q = (self.query or "").strip()
        return c if c else q


def _python_repl_tool() -> BaseTool | None:
    """Python REPL；包装官方工具并统一 ``query`` / ``code`` 形参。"""
    settings = get_settings()
    if not settings.agent_enable_python_repl:
        return None
    try:
        from langchain_experimental.tools import PythonREPLTool as LCPythonREPLTool
    except ImportError:
        logger.warning(
            "已启用 AGENT_ENABLE_PYTHON_REPL 但未安装 langchain-experimental，跳过 python_repl"
        )
        return None

    inner = LCPythonREPLTool(name="_forge_python_repl_inner")
    repl_timeout = _wall_timeout_sec(
        float(settings.python_repl_timeout_sec or 120.0), floor=5.0
    )

    async def _run_python_repl(**kwargs: Any) -> Any:
        """将归一化后的源码交给 LangChain PythonREPLTool；整段执行带墙钟上限。"""
        args = PythonREPLInput.model_validate(kwargs)
        src = args.resolved_source()

        async def _invoke() -> Any:
            return await inner.ainvoke({"query": src})

        try:
            return await asyncio.wait_for(_invoke(), timeout=repl_timeout)
        except TimeoutError:
            return (
                f"Error: python_repl 已超过单次执行时限（{int(repl_timeout)}s）。"
                "代码中的 subprocess.run / input() / 死循环 若不结束会一直阻塞："
                "请为 subprocess.run(..., timeout=秒) 指定超时，并避免交互式脚本。"
            )

    return StructuredTool.from_function(
        name="python_repl",
        description=(
            "在用户进程中执行 Python 代码，适用于计算、简单数据分析或脚本化数据处理。"
            "若需查看输出请使用 print(...)。参数使用 query 或 code 二选一传入源码字符串。"
            f"单次执行最长 {int(repl_timeout)} 秒（含 subprocess 等待）；子进程务必设 timeout。"
            "注意：具备完整进程权限，勿用于不可信输入。"
        ),
        coroutine=_run_python_repl,
        args_schema=PythonREPLInput,
    )


def _shell_tool() -> BaseTool | None:
    """系统 Shell：固定工作目录为 Agent 工作区根 + 子进程超时，避免 CWD 漂移与无超时挂死。"""
    settings = get_settings()
    if not settings.agent_enable_shell_tool:
        return None
    from langchain_community.tools.shell.tool import ShellInput

    timeout_sec = _wall_timeout_sec(float(settings.shell_tool_timeout_sec or 120.0))

    async def _run_shell_forge(**kwargs: Any) -> str:
        """异步子进程执行命令；相对路径相对 AGENT_WORKSPACE_ROOT（默认仓库根）。"""
        args = ShellInput.model_validate(kwargs)
        raw_cmds = args.commands
        if isinstance(raw_cmds, str):
            lines = [raw_cmds.strip()]
        else:
            lines = [str(c).strip() for c in raw_cmds if str(c).strip()]
        if not lines:
            return "Error: empty commands"
        joiner = " & " if platform.system() == "Windows" else " ; "
        script = joiner.join(lines)
        if len(script) > _MAX_SHELL_SCRIPT_CHARS:
            return (
                f"Error: 合并后的命令过长（>{_MAX_SHELL_SCRIPT_CHARS} 字符），请缩短、拆成多次 shell 调用，"
                "或将长脚本写入工作区文件后再执行短命令。"
            )
        if platform.system() == "Windows":
            blocked = _windows_shell_unsupported(script)
            if blocked:
                return blocked
        cwd = str(get_settings().resolved_agent_workspace_path())
        return await _subprocess_shell_output(script, cwd=cwd, timeout_sec=timeout_sec)

    return StructuredTool.from_function(
        name="shell",
        description=(
            "在本机 shell 执行命令（非持久会话）。"
            f"工作目录固定为 Agent 工作区根（与 read_file 等一致），超时 {int(timeout_sec)}s；"
            f"单次合并命令长度上限约 {_MAX_SHELL_SCRIPT_CHARS // 1024}KiB。"
            "**Windows 默认使用 cmd.exe**：`commands` 数组里多条命令会用 ` & ` 连成一行依次执行；"
            "请写 **cmd** 语法（如 `dir /S /B`、`findstr /S /I`、`2>nul`），不要写 bash 的 `find … | xargs`、"
            "`2>/dev/null`、`find -name/-type`；工具会拦截并返回 cmd 等价示例。"
            "Linux/macOS 使用 `/bin/sh` 类 shell，条目间用 ` ; ` 连接。"
            "跨平台复杂检索优先 python -c 或文件工具；高危能力，仅用于受信环境。"
        ),
        coroutine=_run_shell_forge,
        args_schema=ShellInput,
    )


def _build_workspace_tools() -> tuple[BaseTool, ...]:
    """工作区文件工具 + 可选代码与 Shell 工具。"""
    items: list[BaseTool] = list(_build_file_management_tools())
    repl = _python_repl_tool()
    if repl is not None:
        items.append(repl)
    sh = _shell_tool()
    if sh is not None:
        items.append(sh)
    return tuple(items)


def all_builtin_lc_tools() -> tuple[BaseTool, ...]:
    """当前配置下的内置 LangChain 工具；每次调用按最新 Settings 重建。"""
    return (*_build_community_builtin_tools(), *_build_workspace_tools(), list_tools_tool)


def builtin_lc_tools_by_name() -> dict[str, BaseTool]:
    """与 ``execute_builtin`` 分派一致的名称索引（勿模块级缓存，避免 Tavily 密钥变更后仍用旧实例）。"""
    return {t.name: t for t in all_builtin_lc_tools()}


def _parameters_json_schema(tool: BaseTool) -> dict[str, Any] | None:
    """自 LangChain 工具的 ``args_schema`` 生成 JSON Schema。"""
    schema_cls = getattr(tool, "args_schema", None)
    if schema_cls is None:
        return None
    if isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
        return schema_cls.model_json_schema()
    return None


def langchain_tool_to_tool_item(
    tool: BaseTool,
    *,
    source: Literal["builtin", "mcp"] = "builtin",
) -> ToolItem:
    """将已注册的 ``BaseTool`` 转为对外 ``ToolItem``（含 ``parameters`` schema）。"""
    desc = (tool.description or "").strip()
    return ToolItem(
        name=tool.name,
        description=desc if desc else tool.name,
        source=source,
        read_only=True,
        parameters=_parameters_json_schema(tool),
    )


def list_builtin_tools_from_lc() -> list[ToolItem]:
    """由 LangChain 内置工具列表生成 API 用 ``ToolItem``。"""
    return [langchain_tool_to_tool_item(t) for t in all_builtin_lc_tools()]
