"""工作区内置 read_file / write_file：在 LangChain 路径校验之上支持按行局部读写。

与 ``langchain_community.tools.file_management.utils.get_validated_relative_path`` 共用越权检测，
行为与社区版兼容：未指定行范围时读写整文件；write 仍支持 append。列表录仍用社区 ``ListDirectoryTool``。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, model_validator

from langchain_community.tools.file_management.utils import (
    INVALID_PATH_TEMPLATE,
    FileValidationError,
    get_validated_relative_path,
)

_READ_TRUNC_SUFFIX = "\n\n[ForgeAgent read_file: 输出已按 max_chars 截断]"


class ForgeReadFileInput(BaseModel):
    """read_file 工具入参：路径必填，行区间与 max_chars 均为可选。"""

    file_path: str = Field(..., description="工作区相对或根下路径")
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="起始行号（从 1 计）；可与 end_line 组合，或单独表示从该行读到文件末尾",
    )
    end_line: int | None = Field(
        default=None,
        ge=1,
        description="结束行号（从 1 计，含该行）；可与 start_line 组合，或单独表示从第 1 行读到该行",
    )
    max_chars: int | None = Field(
        default=None,
        ge=1,
        description="对最终返回文本的长度上限（Unicode 字符数）；超出则截断并附加提示",
    )

    @model_validator(mode="after")
    def _line_range_ok(self) -> ForgeReadFileInput:
        s, e = self.start_line, self.end_line
        if s is not None and e is not None and e < s:
            raise ValueError("end_line 不得小于 start_line")
        return self


def _truncate_chars(text: str, max_chars: int) -> str:
    """将文本截断到至多 max_chars 个字符，必要时追加提示尾缀。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + _READ_TRUNC_SUFFIX


def _read_file_sync(
    read_path: Path,
    *,
    start_line: int | None,
    end_line: int | None,
    max_chars: int | None,
) -> str:
    """在工作区已解析路径上读取内容；按需做行切片与输出截断。"""
    # 1. 无行界：整文件读
    # 2. 有行界：流式按行迭代，避免大文件一次性载入
    if start_line is None and end_line is None:
        with read_path.open("r", encoding="utf-8") as f:
            content = f.read()
        if max_chars is not None:
            content = _truncate_chars(content, max_chars)
        return content

    start = 1 if start_line is None else start_line
    end = end_line
    parts: list[str] = []
    with read_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if i < start:
                continue
            if end is not None and i > end:
                break
            parts.append(line)
    content = "".join(parts)
    if max_chars is not None:
        content = _truncate_chars(content, max_chars)
    return content


async def _forge_read_file(root: str, **kwargs: Any) -> str:
    """校验路径并异步封装的读文件逻辑。"""
    args = ForgeReadFileInput.model_validate(kwargs)
    root_path = Path(root)
    try:
        read_path = get_validated_relative_path(root_path, args.file_path)
    except FileValidationError:
        return INVALID_PATH_TEMPLATE.format(arg_name="file_path", value=args.file_path)
    if not read_path.exists():
        return f"Error: no such file or directory: {args.file_path}"
    try:

        def _run() -> str:
            return _read_file_sync(
                read_path,
                start_line=args.start_line,
                end_line=args.end_line,
                max_chars=args.max_chars,
            )

        return await asyncio.to_thread(_run)
    except UnicodeDecodeError as e:
        return "Error: " + str(e)
    except OSError as e:
        return "Error: " + str(e)


def build_forge_read_file_tool(root_dir: str) -> StructuredTool:
    """构造与注册名 ``read_file`` 一致的结构化工具。"""

    async def _run(**kw: Any) -> str:
        return await _forge_read_file(root_dir, **kw)

    return StructuredTool.from_function(
        name="read_file",
        description=(
            "读取工作区内的文本文件（UTF-8）。默认读全文。"
            "可选 start_line / end_line（从 1 计的包含区间）：只给 end_line 时从第 1 行读到该行；"
            "只给 start_line 时从该行读到文件末尾；两者都给为闭区间。"
            "可选 max_chars 限制返回字符数，避免极大文件撑爆上下文。"
        ),
        coroutine=_run,
        args_schema=ForgeReadFileInput,
    )


class ForgeWriteFileInput(BaseModel):
    """write_file 工具入参：覆盖、追加或与行区间替换三选一。"""

    file_path: str = Field(..., description="工作区相对或根下路径")
    text: str = Field(..., description="要写入的完整内容或替换片段")
    append: bool = Field(
        default=False,
        description="为 true 时在文件末尾追加 text；不可与行区间替换同时使用",
    )
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="与 end_line 同时给出时，将文件中该闭区间行替换为 text（按行，UTF-8）",
    )
    end_line: int | None = Field(
        default=None,
        ge=1,
        description="行区间结束行（含）；与 start_line 成对使用",
    )

    @model_validator(mode="after")
    def _replace_vs_append(self) -> ForgeWriteFileInput:
        has_s = self.start_line is not None
        has_e = self.end_line is not None
        if has_s ^ has_e:
            raise ValueError("start_line 与 end_line 需成对出现")
        if self.append and has_s:
            raise ValueError("append 为 true 时不支持按行区间替换")
        if has_s and self.end_line is not None and self.end_line < self.start_line: # type: ignore
            raise ValueError("end_line 不得小于 start_line")
        return self


def _write_file_sync(
    root: str,
    args: ForgeWriteFileInput,
) -> str:
    """在工作区已校验路径上执行写入或区间替换。"""
    root_path = Path(root)
    try:
        write_path = get_validated_relative_path(root_path, args.file_path)
    except FileValidationError:
        return INVALID_PATH_TEMPLATE.format(arg_name="file_path", value=args.file_path)

    replace_lines = args.start_line is not None and args.end_line is not None

    try:
        if replace_lines:
            if not write_path.exists():
                return (
                    f"Error: 按行替换要求文件已存在: {args.file_path}"
                )
            with write_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            n = len(lines)
            if args.start_line > n:
                return (
                    f"Error: start_line={args.start_line} 超出文件行数 {n}"
                )
            lo = args.start_line - 1
            hi_exclusive = min(args.end_line, n)
            repl_lines = args.text.splitlines(keepends=True)
            new_lines = lines[:lo] + repl_lines + lines[hi_exclusive:]
            write_path.parent.mkdir(parents=True, exist_ok=True)
            with write_path.open("w", encoding="utf-8") as f:
                f.writelines(new_lines)
            return (
                f"File updated (lines {args.start_line}-{hi_exclusive} replaced) "
                f"at {args.file_path}."
            )

        # 覆盖或追加
        write_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.append else "w"
        with write_path.open(mode, encoding="utf-8") as f:
            f.write(args.text)
        return f"File written successfully to {args.file_path}."
    except OSError as e:
        return "Error: " + str(e)


async def _forge_write_file(root: str, **kwargs: Any) -> str:
    """校验入参并异步封装写文件逻辑。"""
    args = ForgeWriteFileInput.model_validate(kwargs)
    return await asyncio.to_thread(_write_file_sync, root, args)


def build_forge_write_file_tool(root_dir: str) -> StructuredTool:
    """构造与注册名 ``write_file`` 一致的结构化工具。"""

    async def _run(**kw: Any) -> str:
        return await _forge_write_file(root_dir, **kw)

    return StructuredTool.from_function(
        name="write_file",
        description=(
            "写入工作区文本文件（UTF-8）。默认覆盖整文件；append=true 时为末尾追加。"
            "若同时提供 start_line 与 end_line（从 1 计的闭区间），则将文件中该段行替换为 text（"
            "要求文件已存在；text 可为多行）。"
        ),
        coroutine=_run,
        args_schema=ForgeWriteFileInput,
    )
