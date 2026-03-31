"""流式：模型若输出 think 标签则拆两段；无标签则整段为正文（开标签大小写不敏感）。"""

from __future__ import annotations

import re
from typing import Literal

# 标签
_OPEN_RE = re.compile(r"\u003cthink\u003e", re.IGNORECASE)
_CLOSE_RE = re.compile(r"\u003c/think\u003e", re.IGNORECASE)
_OPEN_MARK = "\u003cthink\u003e".lower()
_CLOSE_PLAIN = "\u003c/think\u003e"

Phase = Literal["thinking", "answer"]


def _strip_partial_close_suffix(s: str) -> str:
    """移除字符串末尾的半闭合标签。"""
    sl, cl = s.lower(), _CLOSE_PLAIN.lower()
    for k in range(1, len(cl)):
        if sl.endswith(cl[:k]):
            return s[:-k]
    return s


def _answer_tail_cut(raw: str) -> str:
    """末尾可能是未写完的开标签时，只释放 `<` 之前部分的为正文。"""
    i = raw.rfind("<")
    if i < 0:
        return raw
    tail = raw[i:].lower()
    for k in range(1, min(len(tail), len(_OPEN_MARK)) + 1):
        if _OPEN_MARK.startswith(tail[:k]):
            return raw[:i]
    return raw


def _split_think_answer(raw: str) -> tuple[str, str]:
    """尝试将 `raw` 分割成 `think` 和 `answer`"""
    m_o = _OPEN_RE.search(raw)
    if not m_o:
        return "", _answer_tail_cut(raw)
    i0 = m_o.end()
    m_c = _CLOSE_RE.search(raw, i0)
    if not m_c:
        inner = _strip_partial_close_suffix(raw[i0:])
        return inner, ""
    return raw[i0 : m_c.start()], raw[m_c.end() :]


class ThinkAnswerStream:
    """将模型输出流分割成 think 与 answer。"""

    def __init__(self) -> None:
        self._full = ""
        self._emitted_think = 0
        self._emitted_ans = 0

    @property
    def full_text(self) -> str:
        return self._full

    def feed(self, chunk: str) -> list[tuple[Phase, str]]:
        """输入一个 chunk，返回 think 与 answer 的 delta"""
        if chunk:
            self._full += chunk
        think, ans = _split_think_answer(self._full)
        out: list[tuple[Phase, str]] = []
        if len(think) > self._emitted_think:
            d = think[self._emitted_think :]
            self._emitted_think = len(think)
            if d:
                out.append(("thinking", d))
        if len(ans) > self._emitted_ans:
            d = ans[self._emitted_ans :]
            self._emitted_ans = len(ans)
            if d:
                out.append(("answer", d))
        return out

    def finalize(self) -> list[tuple[Phase, str]]:
        return self.feed("")
