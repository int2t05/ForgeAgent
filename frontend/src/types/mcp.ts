/**
 * MCP 设置 ↔ 表单草稿（Cursor mcpServers、VS Code servers、后端 settings.mcp）。
 */

export type McpTransport = 'mock' | 'stdio' | 'sse' | 'http'

export interface McpMockToolRow {
  name: string
  description: string
  read_only: boolean
}

export interface McpServerDraft {
  localId: string
  name: string
  enabled: boolean
  transport: McpTransport
  command: string
  argsText: string
  url: string
  tools: McpMockToolRow[]
  envText: string
  headersText: string
}

const SSE_KINDS = new Set([
  'sse',
])
const HTTP_KINDS = new Set(['http', 'https', 'streamable-http', 'streamablehttp'])
const STDIO_KINDS = new Set(['stdio', 'stdio-client', 'local', 'shell'])

/** 根级元数据键：不是「服务器名 → 配置」映射。 */
const IGNORED_ROOT_KEYS = new Set([
  'mcp',
  'mcpServers',
  'servers',
  'inputs',
  'version',
  '$schema',
  '__comment',
  'comments',
])

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
    envText: '',
    headersText: '',
  }
}

function normalizeJsonInput(text: string): string {
  return text.replace(/^\uFEFF/, '').trim()
}

function parseJson(text: string, emptyMsg: string): unknown {
  const trimmed = normalizeJsonInput(text)
  if (!trimmed) throw new Error(emptyMsg)
  try {
    return JSON.parse(trimmed) as unknown
  } catch {
    throw new Error('不是合法的 JSON')
  }
}

function scalarStr(v: unknown): string {
  if (typeof v === 'string') return v.trim()
  if (typeof v === 'number') return String(v)
  return ''
}

/** 各客户端对 URL / 命令字段命名不一致。 */
function pickUrl(c: Record<string, unknown>): string {
  return (
    scalarStr(c.url) ||
    scalarStr(c.endpoint) ||
    scalarStr(c.serverUrl) ||
    scalarStr(c.baseUrl) ||
    scalarStr(c.sseUrl) ||
    scalarStr(c.uri)
  )
}

function pickCommand(c: Record<string, unknown>): string {
  return scalarStr(c.command) || scalarStr(c.executable) || scalarStr(c.bin)
}

function argsToText(o: Record<string, unknown>): string {
  const a = o.args
  if (Array.isArray(a)) return a.map((x) => String(x)).join('\n')
  if (typeof a === 'string') return a
  return ''
}

/** 多行 "K=V" 或 "K: V" → 对象（取首个分隔符）。 */
function linesToRecord(text: string, delimiter: '=' | ':'): Record<string, string> {
  const out: Record<string, string> = {}
  for (const raw of text.split('\n')) {
    const i = raw.indexOf(delimiter)
    if (i <= 0) continue
    const k = raw.slice(0, i).trim()
    const v = raw.slice(i + 1).trim()
    if (k) out[k] = v
  }
  return out
}

function objectToEnvLines(obj: Record<string, unknown>): string {
  return Object.entries(obj)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')
}

function objectToHeaderLines(obj: Record<string, unknown>): string {
  return Object.entries(obj)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n')
}

function envRecordToText(c: Record<string, unknown>): string {
  if (typeof c.env === 'string') return c.env
  if (c.env && typeof c.env === 'object' && !Array.isArray(c.env)) {
    const s = objectToEnvLines(c.env as Record<string, unknown>)
    if (s.trim()) return s
  }
  return typeof c.envText === 'string' ? c.envText : ''
}

function headersObjectToText(h: unknown): string {
  if (!h || typeof h !== 'object' || Array.isArray(h)) return ''
  const s = objectToHeaderLines(h as Record<string, unknown>)
  return s.trim()
}

/** 顶层 headers、字符串、requestInit.headers。 */
function headersRecordToText(c: Record<string, unknown>): string {
  if (typeof c.headers === 'string') return c.headers.trim()
  const top = headersObjectToText(c.headers)
  if (top) return top
  const ri = c.requestInit
  if (ri && typeof ri === 'object' && !Array.isArray(ri)) {
    const nested = headersObjectToText((ri as Record<string, unknown>).headers)
    if (nested) return nested
  }
  return typeof c.headersText === 'string' ? c.headersText.trim() : ''
}

function connectionKindFromFields(c: Record<string, unknown>): 'stdio' | 'sse' | 'http' | null {
  const raw = String(c.transport ?? c.type ?? '')
    .toLowerCase()
    .replace(/_/g, '-')
  if (raw === 'mock') return null
  if (STDIO_KINDS.has(raw)) return 'stdio'
  if (HTTP_KINDS.has(raw)) return 'http'
  if (SSE_KINDS.has(raw)) return 'sse'
  return null
}

function inferTransport(o: Record<string, unknown>): McpTransport {
  const kind = connectionKindFromFields(o)
  if (kind === 'stdio') return 'stdio'
  if (kind === 'http') return 'http'
  if (kind === 'sse') return 'sse'
  const raw = String(o.transport ?? o.type ?? '')
    .toLowerCase()
    .replace(/_/g, '-')
  if (raw === 'mock') return 'mock'

  const hasCmd = pickCommand(o).length > 0
  const hasArgs = Array.isArray(o.args) && o.args.length > 0
  const hasUrl = pickUrl(o).length > 0
  if (hasCmd || hasArgs) return 'stdio'
  if (hasUrl) return 'sse'
  return 'mock'
}

function parseOneServer(item: unknown): McpServerDraft | null {
  if (!item || typeof item !== 'object') return null
  const o = item as Record<string, unknown>
  const transport = inferTransport(o)
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
  const argsText = argsToText(o)

  return {
    localId: newLocalId(),
    name: String(o.name ?? ''),
    enabled: o.enabled !== false,
    transport,
    command: pickCommand(o),
    argsText,
    url: pickUrl(o),
    tools:
      transport === 'mock' && tools.length === 0
        ? [{ name: '', description: '', read_only: true }]
        : tools,
    envText: envRecordToText(o),
    headersText: headersRecordToText(o),
  }
}

export function parseMcpListFromApi(raw: unknown[]): McpServerDraft[] {
  if (!Array.isArray(raw)) return []
  return raw.map(parseOneServer).filter((x): x is McpServerDraft => x != null)
}

function isServerConfigLike(v: unknown): boolean {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return false
  const o = v as Record<string, unknown>
  if (connectionKindFromFields(o)) return true
  return Boolean(
    pickUrl(o) ||
      pickCommand(o) ||
      (Array.isArray(o.args) && o.args.length > 0) ||
      typeof o.args === 'string' ||
      o.env ||
      o.headers ||
      o.requestInit ||
      (Array.isArray(o.tools) && o.tools.length > 0),
  )
}

/** 根级别名表：无 mcpServers/servers 包裹时的「服务名 → 配置」。 */
function looksLikeMcpServersFlatMap(o: Record<string, unknown>): boolean {
  const entries = Object.entries(o).filter(([k]) => !IGNORED_ROOT_KEYS.has(k))
  if (entries.length === 0) return false
  return entries.every(([, v]) => isServerConfigLike(v))
}

function toolsFromConfig(c: Record<string, unknown>): unknown[] | undefined {
  if (!Array.isArray(c.tools) || c.tools.length === 0) return undefined
  return c.tools
}

/** mcpServers / servers 对象 → 中间项（再经 parseOneServer）。 */
function mcpServersRecordToItems(mcpServers: Record<string, unknown>): unknown[] {
  const out: unknown[] = []
  for (const [serverKey, config] of Object.entries(mcpServers)) {
    if (config == null || typeof config !== 'object' || Array.isArray(config)) continue
    const c = config as Record<string, unknown>
    const off = c.enabled === false || c.disabled === true
    const name =
      typeof c.name === 'string' && c.name.trim() ? c.name.trim() : serverKey
    const command = pickCommand(c)
    const url = pickUrl(c)
    const kind = connectionKindFromFields(c)
    const argList = Array.isArray(c.args)
      ? c.args.map((a) => String(a))
      : typeof c.args === 'string' && c.args.trim()
        ? [c.args.trim()]
        : []
    const envT = envRecordToText(c).trim()
    const hdrT = headersRecordToText(c).trim()
    const base = { name, ...(off ? { enabled: false } : {}) }
    const toolsPayload = toolsFromConfig(c)

    if (command || kind === 'stdio') {
      out.push({
        ...base,
        transport: 'stdio',
        ...(command ? { command } : {}),
        ...(argList.length ? { args: argList } : {}),
        ...(envT ? { envText: envT } : {}),
        ...(hdrT ? { headersText: hdrT } : {}),
        ...(toolsPayload ? { tools: toolsPayload } : {}),
      })
      continue
    }
    if (url || kind === 'sse' || kind === 'http' || hdrT) {
      out.push({
        ...base,
        transport: kind === 'http' ? 'http' : 'sse',
        ...(url ? { url } : {}),
        ...(envT ? { envText: envT } : {}),
        ...(hdrT ? { headersText: hdrT } : {}),
        ...(toolsPayload ? { tools: toolsPayload } : {}),
      })
      continue
    }
    out.push({
      ...base,
      transport: 'mock',
      ...(toolsPayload ? { tools: toolsPayload } : {}),
    })
  }
  return out
}

function recordToItemsOrEmpty(rec: unknown): unknown[] | null {
  if (!rec || typeof rec !== 'object' || Array.isArray(rec)) return null
  const items = mcpServersRecordToItems(rec as Record<string, unknown>)
  return items.length ? items : null
}

function coerceImportedRootToMcpArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (!data || typeof data !== 'object') {
    throw new Error('根须为 JSON 对象或数组')
  }
  const o = data as Record<string, unknown>
  if (Array.isArray(o.mcp)) return o.mcp

  const merged: unknown[] = []
  for (const key of ['mcpServers', 'servers'] as const) {
    const items = recordToItemsOrEmpty(o[key])
    if (items) merged.push(...items)
  }
  if (merged.length) return merged

  if (looksLikeMcpServersFlatMap(o)) {
    const rest = Object.fromEntries(
      Object.entries(o).filter(([k]) => !IGNORED_ROOT_KEYS.has(k)),
    )
    return mcpServersRecordToItems(rest)
  }

  throw new Error(
    '无法识别：请使用含 mcpServers 或 servers 的 mcp.json，或与之一致的根对象名表（可含 inputs、version 等元数据键）。',
  )
}

/** 粘贴导入：与「完整 JSON」支持相同根格式。 */
export function parseMcpJsonImport(jsonText: string): unknown[] {
  return coerceImportedRootToMcpArray(parseJson(jsonText, '请先粘贴 JSON 内容'))
}

export function parseMcpSingleItemJson(jsonText: string, localId: string): McpServerDraft {
  const data = parseJson(jsonText, 'JSON 不能为空')
  if (data == null || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('单条配置须为 JSON 对象')
  }
  const draft = parseOneServer(data)
  if (!draft) throw new Error('无法识别为有效的 MCP 配置')
  return { ...draft, localId }
}

export function parseFullMcpArrayJson(jsonText: string): McpServerDraft[] {
  const data = parseJson(jsonText, 'JSON 不能为空')
  const arr = coerceImportedRootToMcpArray(data)
  const drafts = parseMcpListFromApi(arr)
  if (drafts.length === 0 && arr.length > 0) {
    throw new Error('数组中无有效的 MCP 对象')
  }
  return drafts
}

export function draftToMcpPayload(d: McpServerDraft): Record<string, unknown> {
  const name = d.name.trim() || 'mcp'
  const out: Record<string, unknown> = {
    name,
    transport: d.transport,
    enabled: d.enabled,
  }

  if (d.transport === 'mock') {
    out.tools = d.tools
      .map((t) => ({
        name: t.name.trim(),
        description: t.description.trim() || undefined,
        read_only: t.read_only,
      }))
      .filter((t) => t.name.length > 0)
  } else if (d.transport === 'stdio') {
    const cmd = d.command.trim()
    if (cmd) out.command = cmd
    const args = d.argsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    if (args.length) out.args = args
    const env = linesToRecord(d.envText.trim(), '=')
    if (Object.keys(env).length) out.env = env
  } else if (d.transport === 'sse' || d.transport === 'http') {
    const url = d.url.trim()
    if (url) out.url = url
    const headers = linesToRecord(d.headersText.trim(), ':')
    if (Object.keys(headers).length) out.headers = headers
  }
  return out
}

export function draftsToMcpPayload(servers: McpServerDraft[]): Record<string, unknown>[] {
  return servers.map(draftToMcpPayload)
}
