/**
 * MCP 服务前端编辑模型（写入 /api/v1/settings 的 mcp[] 项；与后端 mcp_sources 约定对齐）。
 * 注意：服务端禁止字段名包含 api_key、secret、token 等片段。
 */

export type McpTransport = 'mock' | 'stdio' | 'sse'

export interface McpMockToolRow {
  name: string
  description: string
  read_only: boolean
}

/** 单条 MCP 配置（仅用于表单；localId 不落库）。 */
export interface McpServerDraft {
  localId: string
  name: string
  enabled: boolean
  transport: McpTransport
  command: string
  argsText: string
  url: string
  tools: McpMockToolRow[]
}

function newLocalId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `mcp-${Date.now()}-${Math.random()}`
}

export function emptyMcpServerDraft(): McpServerDraft {
  return {
    localId: newLocalId(),
    name: '',
    enabled: true,
    transport: 'mock',
    command: '',
    argsText: '',
    url: '',
    tools: [{ name: '', description: '', read_only: true }],
  }
}

/** 将接口返回的 mcp[] 规范为可编辑草稿。 */
export function parseMcpListFromApi(raw: unknown[]): McpServerDraft[] {
  if (!Array.isArray(raw)) return []
  return raw.map(parseOneServer).filter((x): x is McpServerDraft => x != null)
}

function parseOneServer(item: unknown): McpServerDraft | null {
  if (!item || typeof item !== 'object') return null
  const o = item as Record<string, unknown>
  const tr = String(o.transport ?? 'mock').toLowerCase()
  const transport: McpTransport =
    tr === 'stdio' || tr === 'sse' ? tr : 'mock'

  const tools: McpMockToolRow[] = []
  if (Array.isArray(o.tools)) {
    for (const t of o.tools) {
      if (t && typeof t === 'object' && 'name' in t) {
        const row = t as Record<string, unknown>
        tools.push({
          name: String(row.name ?? ''),
          description: String(row.description ?? ''),
          read_only: row.read_only !== false,
        })
      }
    }
  }

  const argsText = Array.isArray(o.args)
    ? o.args.map((a) => String(a)).join('\n')
    : ''

  return {
    localId: newLocalId(),
    name: String(o.name ?? ''),
    enabled: o.enabled !== false,
    transport,
    command: String(o.command ?? ''),
    argsText,
    url: String(o.url ?? ''),
    tools:
      transport === 'mock' && tools.length === 0
        ? [{ name: '', description: '', read_only: true }]
        : tools,
  }
}

/**
 * 将 Cursor / VS Code 风格的 `mcpServers` 对象转为与本应用一致的 MCP 条目数组。
 * 不解析 env、headers 等敏感或暂不支持的字段；导入后可在表单中补全。
 */
function mcpServersRecordToItems(mcpServers: Record<string, unknown>): unknown[] {
  const out: unknown[] = []
  for (const [serverKey, config] of Object.entries(mcpServers)) {
    if (config == null || typeof config !== 'object' || Array.isArray(config)) continue
    const c = config as Record<string, unknown>
    const disabled = c.enabled === false || c.disabled === true
    const nameFromInner =
      typeof c.name === 'string' && c.name.trim() ? c.name.trim() : undefined
    const name = nameFromInner ?? serverKey

    const commandRaw = c.command
    const command =
      typeof commandRaw === 'string'
        ? commandRaw.trim()
        : typeof commandRaw === 'number'
          ? String(commandRaw)
          : ''

    const urlRaw = c.url
    const url =
      typeof urlRaw === 'string'
        ? urlRaw.trim()
        : typeof urlRaw === 'number'
          ? String(urlRaw)
          : ''

    const transportHint = String(c.transport ?? '').toLowerCase()

    if (command || transportHint === 'stdio') {
      const args = Array.isArray(c.args) ? c.args.map((a) => String(a)) : []
      out.push({
        name,
        transport: 'stdio',
        ...(command ? { command } : {}),
        ...(args.length ? { args } : {}),
        ...(disabled ? { enabled: false } : {}),
      })
      continue
    }

    if (url || transportHint === 'sse' || transportHint === 'http') {
      out.push({
        name,
        transport: 'sse',
        ...(url ? { url } : {}),
        ...(disabled ? { enabled: false } : {}),
      })
      continue
    }

    out.push({
      name,
      transport: 'mock',
      tools: [],
      ...(disabled ? { enabled: false } : {}),
    })
  }
  return out
}

/**
 * 从粘贴的 JSON 文本解析 mcp 数组（与 PUT /settings 的 mcp 字段一致）。
 * 支持：
 * - 根为 MCP 对象数组
 * - `{ "mcp": [...] }`（与 GET /settings 一致）
 * - `{ "mcpServers": { "别名": { "command", "args", "url", … } } }`（Cursor mcp.json）
 */
export function parseMcpJsonImport(jsonText: string): unknown[] {
  const trimmed = jsonText.trim()
  if (!trimmed) throw new Error('请先粘贴 JSON 内容')

  let data: unknown
  try {
    data = JSON.parse(trimmed) as unknown
  } catch {
    throw new Error('不是合法的 JSON')
  }

  if (Array.isArray(data)) return data

  if (data && typeof data === 'object') {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.mcp)) return o.mcp

    const ms = o.mcpServers
    if (ms && typeof ms === 'object' && !Array.isArray(ms)) {
      const items = mcpServersRecordToItems(ms as Record<string, unknown>)
      if (items.length === 0) {
        throw new Error('mcpServers 为空或无可识别的条目')
      }
      return items
    }
  }

  throw new Error(
    '须为：MCP 对象数组、{ "mcp": [...] } 或 Cursor 的 { "mcpServers": { ... } }',
  )
}

/**
 * 将单条后端形态的 MCP JSON 文本解析为草稿（保留原有 localId）。
 * @throws Error 解析失败或不是对象
 */
export function parseMcpSingleItemJson(jsonText: string, localId: string): McpServerDraft {
  const trimmed = jsonText.trim()
  if (!trimmed) throw new Error('JSON 不能为空')
  let data: unknown
  try {
    data = JSON.parse(trimmed) as unknown
  } catch {
    throw new Error('不是合法的 JSON')
  }
  if (data == null || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('单条配置须为 JSON 对象')
  }
  const draft = parseOneServer(data)
  if (!draft) throw new Error('无法识别为有效的 MCP 配置')
  return { ...draft, localId }
}

/** 解析完整 mcp[] JSON（与 GET/PUT settings 的 mcp 字段一致）。 */
export function parseFullMcpArrayJson(jsonText: string): McpServerDraft[] {
  const trimmed = jsonText.trim()
  if (!trimmed) throw new Error('JSON 不能为空')
  let data: unknown
  try {
    data = JSON.parse(trimmed) as unknown
  } catch {
    throw new Error('不是合法的 JSON')
  }
  const arr = Array.isArray(data) ? data : null
  if (!arr) throw new Error('须为 JSON 数组，例如 [ {...}, {...} ]')
  const drafts = parseMcpListFromApi(arr)
  if (drafts.length === 0 && arr.length > 0) {
    throw new Error('数组中无有效的 MCP 对象')
  }
  return drafts
}

/** 序列化为写入 settings 的对象（无 localId）。 */
export function draftToMcpPayload(d: McpServerDraft): Record<string, unknown> {
  const name = d.name.trim() || 'mcp'
  const out: Record<string, unknown> = {
    name,
    transport: d.transport,
  }
  if (d.enabled === false) out.enabled = false

  if (d.transport === 'mock') {
    const tools = d.tools
      .map((t) => ({
        name: t.name.trim(),
        description: t.description.trim() || undefined,
        read_only: t.read_only,
      }))
      .filter((t) => t.name.length > 0)
    out.tools = tools
  } else if (d.transport === 'stdio') {
    const cmd = d.command.trim()
    if (cmd) out.command = cmd
    const args = d.argsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    if (args.length) out.args = args
  } else {
    const url = d.url.trim()
    if (url) out.url = url
  }

  return out
}

export function draftsToMcpPayload(servers: McpServerDraft[]): Record<string, unknown>[] {
  return servers.map(draftToMcpPayload)
}
