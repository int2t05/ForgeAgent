/**
 * 与后端 `stream_split.py` 对齐：从模型输出缓冲区中分离首段 `think`（支持流式未闭合）。
 */

const _OPEN_RE = /\u003cthink\u003e/i
const _CLOSE_RE = /\u003c\/think\u003e/i
const _OPEN_MARK = '\u003cthink\u003e'.toLowerCase()
const _CLOSE_PLAIN = '\u003c/think\u003e'

function stripPartialCloseSuffix(s: string): string {
  const sl = s.toLowerCase()
  const cl = _CLOSE_PLAIN.toLowerCase()
  for (let k = cl.length - 1; k >= 1; k--) {
    if (sl.endsWith(cl.slice(0, k))) return s.slice(0, -k)
  }
  return s
}

function answerTailCut(raw: string): string {
  const i = raw.lastIndexOf('<')
  if (i < 0) return raw
  const tail = raw.slice(i).toLowerCase()
  for (let k = 1; k <= Math.min(tail.length, _OPEN_MARK.length); k++) {
    if (_OPEN_MARK.startsWith(tail.slice(0, k))) return raw.slice(0, i)
  }
  return raw
}

/** 与 `stream_split._split_think_answer` 一致 */
function splitThinkAnswerRaw(raw: string): { think: string; answer: string } {
  const mO = raw.match(_OPEN_RE)
  if (!mO || mO.index === undefined) {
    return { think: '', answer: answerTailCut(raw) }
  }
  const i0 = mO.index + mO[0].length
  const afterOpen = raw.slice(i0)
  const mC = afterOpen.match(_CLOSE_RE)
  if (!mC || mC.index === undefined) {
    return { think: stripPartialCloseSuffix(afterOpen), answer: '' }
  }
  const think = afterOpen.slice(0, mC.index)
  const answer = afterOpen.slice(mC.index + mC[0].length)
  return { think, answer }
}

/** 从 answer 流缓冲区剥出 think 内文；可见正文不含未闭合标签残片。 */
export function peelLeadingThinkBlockFromBuffer(raw: string): {
  think: string
  visible: string
} {
  const { think, answer } = splitThinkAnswerRaw(raw)
  return { think: think.trim(), visible: answer }
}
