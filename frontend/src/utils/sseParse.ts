/**
 * SSE 文本分帧与 data 解析（与后端 event_stream_service 输出格式对齐）。
 */

/**
 * 从缓冲区中切出完整 SSE 报文块（以连续两个换行分隔），返回剩余未完成片段。
 */
export function splitSseBlocks(buffer: string): { blocks: string[]; rest: string } {
  const blocks: string[] = []
  let i = 0
  while (i < buffer.length) {
    const sep = buffer.indexOf('\n\n', i)
    if (sep === -1) {
      return { blocks, rest: buffer.slice(i) }
    }
    blocks.push(buffer.slice(i, sep))
    i = sep + 2
  }
  return { blocks, rest: '' }
}

/**
 * 解析单条 SSE 块：提取 `data:` 行并合并为多行 data 标准语义。
 */
export function parseSseDataJson(block: string): string | null {
  const lines = block.split(/\r?\n/)
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) {
    return null
  }
  return dataLines.join('\n')
}
