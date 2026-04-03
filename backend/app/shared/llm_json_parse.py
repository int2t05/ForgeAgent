"""从大模型输出文本中解析单个 JSON 对象（规划 / ReAct 路由等共用）。

多候选、围栏块、尾逗号、弯引号、类 Python 字面量等纠偏。
"""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SMART_QUOTE_TRANS = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u00ab": '"',
        "\u00bb": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u2032": "'",
    }
)


def _strip_markdown_json_fence(text: str) -> str:
    """去掉 Markdown 中的 JSON 围栏（整段以围栏开头时）。"""
    t = text.strip()
    if not t.startswith("```"):
        return t
    t = re.sub(r"^```(?:json)?\s*", "", t, count=1, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _normalize_llm_text_noise(text: str) -> str:
    """去掉 BOM、零宽字符等常见噪声。"""
    t = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace(
        "\u200d", ""
    )
    return t


def _repair_trailing_commas(s: str) -> str:
    """去掉对象/数组末尾多余逗号（模型常见 ``{\"a\":1,}``）。"""
    out = s
    prev = ""
    while prev != out:
        prev = out
        out = re.sub(r",(\s*[}\]])", r"\1", out)
    return out


def _iter_markdown_fence_bodies(text: str) -> list[str]:
    """提取文本中所有 ``` / ```json 代码块内容（按出现顺序）。"""
    return [
        m.group(1).strip()
        for m in re.finditer(
            r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE
        )
        if m.group(1).strip()
    ]


def _first_balanced_json_object(text: str) -> str | None:
    """自首个「不在字符串内的」`{` 起，匹配与之成对的 `}`，返回子串（RFC JSON 风格双引号串）。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _first_balanced_braced_literal(text: str) -> str | None:
    """自首个 ``{`` 起做括号配平；字符串内支持 ``"`` 与 ``'``（便于再交给 ``literal_eval``）。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    string_delim = ""
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == string_delim:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            string_delim = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_ast_literal_eval_dict(s: str) -> dict[str, Any] | None:
    """将类 Python 字面量对象（单引号键值、True/None 等）安全解析为 dict。"""
    s = s.strip()
    if not s.startswith("{"):
        return None
    try:
        val = ast.literal_eval(s)
    except (ValueError, SyntaxError, TypeError):
        return None
    return val if isinstance(val, dict) else None


def _json_decode_dict_from_slice(dec: json.JSONDecoder, s: str) -> dict[str, Any] | None:
    """从整段或任意 ``{`` 起尝试 ``JSONDecoder.raw_decode``；仅接受「解析后无尾部垃圾」的命中，避免嵌套 ``{}`` 误当成根对象。"""
    s = s.strip()
    if not s:
        return None

    def _consume_all(obj: Any, end: int) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        if s[end:].strip():
            return None
        return obj

    try:
        obj, end = dec.raw_decode(s)
        got = _consume_all(obj, end)
        if got is not None:
            return got
    except json.JSONDecodeError:
        pass
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, end = dec.raw_decode(s, i)
        except json.JSONDecodeError:
            continue
        got = _consume_all(obj, end)
        if got is not None:
            return got
    return None


def try_parse_single_candidate(candidate: str) -> dict[str, Any] | None:
    """对单段候选串依次：标准 JSON、括号切片、``literal_eval``。"""
    dec = json.JSONDecoder()
    variants: list[str] = []
    seen: set[str] = set()

    def _push(raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        for v in (
            raw,
            _repair_trailing_commas(raw),
            raw.translate(_SMART_QUOTE_TRANS),
            _repair_trailing_commas(raw.translate(_SMART_QUOTE_TRANS)),
        ):
            t = v.strip()
            if t and t not in seen:
                seen.add(t)
                variants.append(t)

    cand = _strip_markdown_json_fence(candidate.strip())
    _push(_normalize_llm_text_noise(cand))

    for v in list(variants):
        got = _json_decode_dict_from_slice(dec, v)
        if got is not None:
            return got
        bal_json = _first_balanced_json_object(v)
        if bal_json:
            _push(bal_json)
        bal_lit = _first_balanced_braced_literal(v)
        if bal_lit and bal_lit != bal_json:
            _push(bal_lit)

    for v in variants:
        got = _json_decode_dict_from_slice(dec, v)
        if got is not None:
            return got
        bal_lit = _first_balanced_braced_literal(v)
        if bal_lit:
            got = _json_decode_dict_from_slice(dec, bal_lit)
            if got is not None:
                return got
            le = _try_ast_literal_eval_dict(bal_lit)
            if le is not None:
                return le
    return None


def _strip_think_tags(text: str) -> str:
    """剥离所有 &lt;think&gt;...&lt;/think&gt; 标签块（包括未闭合的开头），返回剩余文本。"""
    import re
    # 模式1：完整的 &lt;think&gt;...&lt;/think&gt; 标签对（不区分大小写，支持中间换行）
    pattern_complete = re.compile(r"&lt;think&gt;[\s\S]*?&lt;/think&gt;", re.IGNORECASE)
    # 模式2：未闭合的 &lt;think&gt; 开头（到文本末尾或下一个非空格字符前）
    pattern_unclosed = re.compile(r"&lt;think&gt;.*$", re.IGNORECASE | re.DOTALL)
    
    t = text
    # 先替换完整的标签对
    t = pattern_complete.sub("", t)
    # 再替换未闭合的标签开头
    t = pattern_unclosed.sub("", t)
    return t.strip()


def collect_json_candidates(text: str) -> list[str]:
    """合并全文与所有围栏块、去重保序。"""
    base = _normalize_llm_text_noise(text).strip()
    out: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    add(base)
    no_think = _strip_think_tags(base)
    if no_think:
        add(no_think)
    for body in _iter_markdown_fence_bodies(base):
        add(body)
        add(_strip_think_tags(body))
    return out


def parse_llm_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出文本中解析单个 JSON 对象，失败时返回 None。"""
    if not text or not str(text).strip():
        return None
    for cand in collect_json_candidates(text):
        got = try_parse_single_candidate(cand)
        if got is not None:
            return got
    logger.debug(
        "could not parse JSON object from model text (len=%s, head=%r)",
        len(text),
        text[:400].replace("\n", "\\n"),
    )
    return None


__all__ = [
    "collect_json_candidates",
    "parse_llm_json_object",
    "try_parse_single_candidate",
]
