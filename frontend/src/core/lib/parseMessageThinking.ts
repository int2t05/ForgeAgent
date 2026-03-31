/**
 * 从助手消息正文剥离前置「思考」块，供折叠展示。
 * 支持：<think>...</think>、<think>、以及 Markdown ```思考 代码围栏。
 */

export interface ThinkingSplit {
  thinking: string | null
  /** 供 Markdown 渲染的主正文 */
  body: string
}

const RE_XML_THINK =
  /^\s*\u003cthink\u003e([\s\S]*?)\u003c\/think\u003e\s*/i
const RE_XML_REDACTED =
  /^\s*\u003credacted_reasoning\u003e([\s\S]*?)\u003c\/redacted_reasoning\u003e\s*/i

const FENCE_BLOCK =
  /^\s*```(?:\s*)(?:思考|thinking|thought|reasoning|think)\s*\n([\s\S]*?)```\s*\n?/i

/**
 * 循环剥离开头的思考块，避免多重包裹。
 */
export function splitThinkingFromMessage(text: string): ThinkingSplit {
  let remainder = text
  const chunks: string[] = []
  const maxPasses = 8

  for (let i = 0; i < maxPasses; i++) {
    const xmlThink = remainder.match(RE_XML_THINK)
    const xmlRed = xmlThink ? null : remainder.match(RE_XML_REDACTED)
    const xml = xmlThink ?? xmlRed
    if (xml) {
      const inner = xml[1].trim()
      if (inner) chunks.push(inner)
      remainder = remainder.slice(xml[0].length)
      continue
    }
    const fence = remainder.match(FENCE_BLOCK)
    if (fence) {
      const inner = fence[1].trim()
      if (inner) chunks.push(inner)
      remainder = remainder.slice(fence[0].length)
      continue
    }
    break
  }

  const thinking = chunks.length > 0 ? chunks.join('\n\n———\n\n') : null
  return { thinking, body: remainder.trimStart() }
}
