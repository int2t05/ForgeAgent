/**
 * MCP 服务列表编辑器：与后端 settings.mcp[] 及 mcp_sources 约定对齐。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  type McpServerDraft,
  type McpMockToolRow,
  type McpTransport,
  draftToMcpPayload,
  draftsToMcpPayload,
  emptyMcpServerDraft,
  parseFullMcpArrayJson,
  parseMcpJsonImport,
  parseMcpListFromApi,
  parseMcpSingleItemJson,
} from '@/types/mcp'

interface McpServersEditorProps {
  servers: McpServerDraft[]
  onChange: (servers: McpServerDraft[]) => void
}

type ServerEditMode = 'form' | 'json'

const TRANSPORT_OPTIONS: Array<{ value: McpTransport; label: string }> = [
  { value: 'mock', label: 'Mock（内嵌工具元数据，当前可注册到工具表）' },
  { value: 'stdio', label: 'Stdio（命令行；配置可先保存，运行时接入后生效）' },
  { value: 'sse', label: 'SSE（URL；配置可先保存，运行时接入后生效）' },
]

function updateServer(
  servers: McpServerDraft[],
  localId: string,
  patch: Partial<McpServerDraft>,
): McpServerDraft[] {
  return servers.map((s) => (s.localId === localId ? { ...s, ...patch } : s))
}

export function McpServersEditor({ servers, onChange }: McpServersEditorProps) {
  const [importPaste, setImportPaste] = useState('')
  const [importError, setImportError] = useState<string | null>(null)

  const canonicalFullJson = useMemo(
    () => JSON.stringify(draftsToMcpPayload(servers), null, 2),
    [servers],
  )
  const [fullMcpText, setFullMcpText] = useState(canonicalFullJson)
  const fullMcpFocusedRef = useRef(false)
  const [fullMcpError, setFullMcpError] = useState<string | null>(null)

  useEffect(() => {
    if (!fullMcpFocusedRef.current) setFullMcpText(canonicalFullJson)
  }, [canonicalFullJson])

  const [serverModes, setServerModes] = useState<Record<string, ServerEditMode>>({})
  const [serverJsonDraft, setServerJsonDraft] = useState<Record<string, string>>({})
  const [serverJsonError, setServerJsonError] = useState<Record<string, string>>({})

  function serverMode(id: string): ServerEditMode {
    return serverModes[id] ?? 'form'
  }

  function setModeForServer(id: string, mode: ServerEditMode) {
    if (mode === 'json') {
      const s = servers.find((x) => x.localId === id)
      if (s) {
        setServerJsonDraft((prev) => ({
          ...prev,
          [id]: JSON.stringify(draftToMcpPayload(s), null, 2),
        }))
      }
      setServerJsonError((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    }
    setServerModes((prev) => ({ ...prev, [id]: mode }))
  }

  function applyFullMcpJson() {
    try {
      const next = parseFullMcpArrayJson(fullMcpText)
      onChange(next)
      setFullMcpError(null)
    } catch (e) {
      setFullMcpError(e instanceof Error ? e.message : '应用失败')
    }
  }

  function applyServerJson(localId: string) {
    const text = serverJsonDraft[localId] ?? ''
    try {
      const d = parseMcpSingleItemJson(text, localId)
      onChange(servers.map((s) => (s.localId === localId ? d : s)))
      setServerJsonError((prev) => {
        const next = { ...prev }
        delete next[localId]
        return next
      })
    } catch (e) {
      setServerJsonError((prev) => ({
        ...prev,
        [localId]: e instanceof Error ? e.message : '解析失败',
      }))
    }
  }

  function applyPastedJson() {
    try {
      const arr = parseMcpJsonImport(importPaste)
      const drafts = parseMcpListFromApi(arr)
      if (drafts.length === 0 && arr.length > 0) {
        throw new Error('JSON 中无有效的 MCP 对象（每项须为对象）')
      }
      onChange(drafts)
      setImportError(null)
      setServerModes({})
      setServerJsonDraft({})
      setServerJsonError({})
    } catch (err) {
      setImportError(err instanceof Error ? err.message : '导入失败')
    }
  }

  function addServer() {
    onChange([...servers, emptyMcpServerDraft()])
  }

  function removeServer(localId: string) {
    onChange(servers.filter((s) => s.localId !== localId))
    setServerModes((prev) => {
      const next = { ...prev }
      delete next[localId]
      return next
    })
    setServerJsonDraft((prev) => {
      const next = { ...prev }
      delete next[localId]
      return next
    })
    setServerJsonError((prev) => {
      const next = { ...prev }
      delete next[localId]
      return next
    })
  }

  function patchServer(localId: string, patch: Partial<McpServerDraft>) {
    onChange(updateServer(servers, localId, patch))
  }

  function setTransport(localId: string, transport: McpTransport) {
    const s = servers.find((x) => x.localId === localId)
    if (!s) return
    if (transport === 'mock') {
      onChange(
        updateServer(servers, localId, {
          transport,
          tools:
            s.tools.length > 0
              ? s.tools
              : [{ name: '', description: '', read_only: true }],
        }),
      )
    } else {
      onChange(updateServer(servers, localId, { transport }))
    }
  }

  function addToolRow(serverId: string) {
    const s = servers.find((x) => x.localId === serverId)
    if (!s) return
    const tools: McpMockToolRow[] = [
      ...s.tools,
      { name: '', description: '', read_only: true },
    ]
    patchServer(serverId, { tools })
  }

  function patchTool(
    serverId: string,
    toolIndex: number,
    patch: Partial<McpMockToolRow>,
  ) {
    const s = servers.find((x) => x.localId === serverId)
    if (!s) return
    const tools = s.tools.map((t, i) => (i === toolIndex ? { ...t, ...patch } : t))
    patchServer(serverId, { tools })
  }

  function removeTool(serverId: string, toolIndex: number) {
    const s = servers.find((x) => x.localId === serverId)
    if (!s) return
    const tools = s.tools.filter((_, i) => i !== toolIndex)
    patchServer(serverId, {
      tools:
        tools.length > 0
          ? tools
          : [{ name: '', description: '', read_only: true }],
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <p className="text-neutral-500 text-xs leading-relaxed sm:max-w-[75%]">
          当前进程内仅 <strong className="text-neutral-700">transport=mock</strong>{' '}
          且提供 <code className="rounded bg-neutral-100 px-1 font-mono text-[11px]">tools[]</code>{' '}
          时会将工具注册到{' '}
          <code className="rounded bg-neutral-100 px-1 font-mono text-[11px]">GET /api/v1/tools</code>
          ；Stdio/SSE 可先填写并保存。请勿在 JSON 中含 api_key、secret、token 等字段名（服务端会拒绝）。
        </p>
      </div>

      <details className="group/full fa-card border-neutral-200/85 overflow-hidden open:shadow-sm">
        <summary className="cursor-pointer list-none px-4 py-3 font-medium text-neutral-800 text-sm [&::-webkit-details-marker]:hidden">
          <span className="mr-2 inline-block text-neutral-400 transition-transform group-open/full:rotate-90">
            ▸
          </span>
          完整 mcp[] JSON（与 GET/PUT <code className="font-mono text-xs">settings.mcp</code> 一致）
        </summary>
        <div className="space-y-2 border-neutral-100 border-t px-4 py-3">
          <p className="text-neutral-500 text-xs leading-relaxed">
            可直接编辑后端形态的数组；失焦单项卡片后此处会随列表更新（正在编辑本框时不会覆盖）。
            修改后点「应用全文」替换下方全部 MCP。
          </p>
          <textarea
            value={fullMcpText}
            onChange={(e) => setFullMcpText(e.target.value)}
            onFocus={() => {
              fullMcpFocusedRef.current = true
            }}
            onBlur={() => {
              fullMcpFocusedRef.current = false
            }}
            spellCheck={false}
            rows={12}
            className="fa-input max-h-[min(360px,50vh)] w-full resize-y font-mono text-xs leading-relaxed"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="fa-btn-secondary text-xs"
              onClick={applyFullMcpJson}
            >
              应用全文到列表
            </button>
            <button
              type="button"
              className="rounded px-2 py-1 text-neutral-600 text-xs hover:bg-neutral-100 hover:text-neutral-900"
              onClick={() => {
                setFullMcpText(canonicalFullJson)
                setFullMcpError(null)
              }}
            >
              从当前列表重置文本
            </button>
          </div>
          {fullMcpError && (
            <p className="text-red-600 text-xs">{fullMcpError}</p>
          )}
        </div>
      </details>

      <div className="fa-card border-neutral-200/85 p-3">
        <p className="fa-kv-label mb-2 block">快速导入：粘贴 mcp.json 全文</p>
        <p className="mb-2 text-neutral-500 text-xs leading-relaxed">
          支持 Cursor / VS Code 的{' '}
          <code className="rounded bg-neutral-100 px-1 font-mono text-[11px]">
            mcpServers
          </code>{' '}
          结构，或本应用{' '}
          <code className="rounded bg-neutral-100 px-1 font-mono text-[11px]">mcp</code>{' '}
          数组。将替换下方当前列表（不含 env 等密钥字段，请勿粘贴含密钥的片段）。
        </p>
        <textarea
          value={importPaste}
          onChange={(e) => setImportPaste(e.target.value)}
          rows={5}
          spellCheck={false}
          className="fa-input mb-2 max-h-40 w-full resize-y font-mono text-xs"
          placeholder={`{\n  "mcpServers": {\n    "filesystem": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]\n    }\n  }\n}`}
        />
        <button
          type="button"
          className="fa-btn-secondary text-xs"
          onClick={applyPastedJson}
        >
          识别并替换列表
        </button>
      </div>

      {importError && (
        <p className="text-red-600 text-xs leading-relaxed">{importError}</p>
      )}

      {servers.length === 0 && (
        <div className="fa-card border-dashed border-neutral-300/80 bg-neutral-50/50 px-4 py-8 text-center text-neutral-500 text-sm">
          暂无 MCP 条目，点击下方按钮添加。
        </div>
      )}

      <ul className="space-y-3">
        {servers.map((s, idx) => {
          const mode = serverMode(s.localId)
          const title =
            s.name.trim() || `(未命名 #${idx + 1})`
          return (
            <li key={s.localId}>
              <details className="fa-card group border-neutral-200/85 overflow-hidden open:shadow-sm">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm [&::-webkit-details-marker]:hidden">
                  <span className="text-neutral-400 select-none transition-transform group-open:rotate-90">
                    ▸
                  </span>
                  <span className="font-medium text-neutral-900">{title}</span>
                  <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[11px] text-neutral-600">
                    {s.transport}
                  </code>
                  {!s.enabled && (
                    <span className="rounded bg-neutral-200/80 px-1.5 py-0.5 text-[11px] text-neutral-600">
                      已禁用
                    </span>
                  )}
                  <span className="ml-auto font-display text-neutral-400 text-xs tabular-nums">
                    #{idx + 1}
                  </span>
                </summary>

                <div className="space-y-4 border-neutral-100 border-t px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex rounded-lg border border-neutral-200/90 p-0.5">
                      <button
                        type="button"
                        className={`rounded-md px-2.5 py-1 text-xs ${
                          mode === 'form'
                            ? 'bg-white font-medium text-neutral-900 shadow-sm'
                            : 'text-neutral-500 hover:text-neutral-800'
                        }`}
                        onClick={(e) => {
                          e.preventDefault()
                          setModeForServer(s.localId, 'form')
                        }}
                      >
                        可视化
                      </button>
                      <button
                        type="button"
                        className={`rounded-md px-2.5 py-1 text-xs ${
                          mode === 'json'
                            ? 'bg-white font-medium text-neutral-900 shadow-sm'
                            : 'text-neutral-500 hover:text-neutral-800'
                        }`}
                        onClick={(e) => {
                          e.preventDefault()
                          setModeForServer(s.localId, 'json')
                        }}
                      >
                        JSON
                      </button>
                    </div>
                    <button
                      type="button"
                      className="fa-btn-text-danger py-1 text-xs"
                      onClick={(e) => {
                        e.preventDefault()
                        removeServer(s.localId)
                      }}
                    >
                      移除此项
                    </button>
                  </div>

                  {mode === 'json' ? (
                    <div className="space-y-2">
                      <p className="text-neutral-500 text-xs">
                        单条对象格式与写入 <code className="font-mono">mcp[]</code> 的元素一致（无 localId）。
                      </p>
                      <textarea
                        value={
                          serverJsonDraft[s.localId] ??
                          JSON.stringify(draftToMcpPayload(s), null, 2)
                        }
                        onChange={(e) =>
                          setServerJsonDraft((prev) => ({
                            ...prev,
                            [s.localId]: e.target.value,
                          }))
                        }
                        spellCheck={false}
                        rows={14}
                        className="fa-input max-h-[min(320px,40vh)] w-full resize-y font-mono text-xs leading-relaxed"
                      />
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="fa-btn-secondary text-xs"
                          onClick={() => applyServerJson(s.localId)}
                        >
                          应用 JSON 到此项
                        </button>
                        <button
                          type="button"
                          className="rounded px-2 py-1 text-neutral-600 text-xs hover:bg-neutral-100 hover:text-neutral-900"
                          onClick={() =>
                            setServerJsonDraft((prev) => ({
                              ...prev,
                              [s.localId]: JSON.stringify(
                                draftToMcpPayload(s),
                                null,
                                2,
                              ),
                            }))
                          }
                        >
                          从当前项重置
                        </button>
                      </div>
                      {serverJsonError[s.localId] && (
                        <p className="text-red-600 text-xs">
                          {serverJsonError[s.localId]}
                        </p>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <label className="block sm:col-span-2">
                          <span className="fa-kv-label mb-1 block">显示名称 / name</span>
                          <input
                            type="text"
                            value={s.name}
                            onChange={(e) =>
                              patchServer(s.localId, { name: e.target.value })
                            }
                            className="fa-input py-2 text-sm"
                            placeholder="例如 filesystem"
                            autoComplete="off"
                          />
                        </label>

                        <label className="flex items-center gap-2 sm:col-span-2">
                          <input
                            type="checkbox"
                            checked={s.enabled}
                            onChange={(e) =>
                              patchServer(s.localId, { enabled: e.target.checked })
                            }
                            className="rounded border-neutral-300 text-primary-600 focus:ring-primary-500/30"
                          />
                          <span className="text-neutral-700 text-sm">启用该 MCP</span>
                        </label>

                        <label className="block sm:col-span-2">
                          <span className="fa-kv-label mb-1 block">传输方式 / transport</span>
                          <select
                            value={s.transport}
                            onChange={(e) =>
                              setTransport(s.localId, e.target.value as McpTransport)
                            }
                            className="fa-select w-full max-w-xl"
                          >
                            {TRANSPORT_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>

                      {s.transport === 'mock' && (
                        <div className="mt-2 border-neutral-100 border-t pt-4">
                          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                            <span className="fa-section-title !mb-0">Mock 工具列表</span>
                            <button
                              type="button"
                              className="fa-btn-secondary text-xs"
                              onClick={() => addToolRow(s.localId)}
                            >
                              + 工具
                            </button>
                          </div>
                          <ul className="space-y-2">
                            {s.tools.map((t, ti) => (
                              <li key={`${s.localId}-tool-${ti}`}>
                                <details className="group/tool rounded-lg border border-neutral-200/80 bg-neutral-50/50 open:bg-white/60">
                                  <summary className="cursor-pointer list-none px-3 py-2 text-sm [&::-webkit-details-marker]:hidden">
                                    <span className="mr-2 inline-block text-neutral-400 transition-transform group-open/tool:rotate-90">
                                      ▸
                                    </span>
                                    <code className="font-mono text-[13px]">
                                      {t.name.trim() || `(工具 #${ti + 1})`}
                                    </code>
                                  </summary>
                                  <div className="space-y-2 px-3 pb-3 pt-0">
                                    <div className="flex justify-end">
                                      <button
                                        type="button"
                                        className="text-neutral-500 text-xs hover:text-red-600"
                                        onClick={(e) => {
                                          e.preventDefault()
                                          removeTool(s.localId, ti)
                                        }}
                                      >
                                        删除工具
                                      </button>
                                    </div>
                                    <div className="grid gap-2 sm:grid-cols-2">
                                      <label className="block">
                                        <span className="fa-kv-label mb-1 block">工具名 name</span>
                                        <input
                                          type="text"
                                          value={t.name}
                                          onChange={(e) =>
                                            patchTool(s.localId, ti, {
                                              name: e.target.value,
                                            })
                                          }
                                          className="fa-input py-2 text-sm font-mono"
                                          placeholder="read_file"
                                        />
                                      </label>
                                      <label className="flex items-center gap-2 sm:col-span-2">
                                        <input
                                          type="checkbox"
                                          checked={t.read_only}
                                          onChange={(e) =>
                                            patchTool(s.localId, ti, {
                                              read_only: e.target.checked,
                                            })
                                          }
                                          className="rounded border-neutral-300 text-primary-600"
                                        />
                                        <span className="text-neutral-600 text-xs">
                                          只读 read_only
                                        </span>
                                      </label>
                                      <label className="block sm:col-span-2">
                                        <span className="fa-kv-label mb-1 block">
                                          描述 description
                                        </span>
                                        <input
                                          type="text"
                                          value={t.description}
                                          onChange={(e) =>
                                            patchTool(s.localId, ti, {
                                              description: e.target.value,
                                            })
                                          }
                                          className="fa-input py-2 text-sm"
                                          placeholder="工具说明（展示在工具表）"
                                        />
                                      </label>
                                    </div>
                                  </div>
                                </details>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {s.transport === 'stdio' && (
                        <div className="mt-4 grid gap-3 border-neutral-100 border-t pt-4 sm:grid-cols-2">
                          <label className="block sm:col-span-2">
                            <span className="fa-kv-label mb-1 block">可执行命令 command</span>
                            <input
                              type="text"
                              value={s.command}
                              onChange={(e) =>
                                patchServer(s.localId, { command: e.target.value })
                              }
                              className="fa-input py-2 font-mono text-sm"
                              placeholder="npx"
                              autoComplete="off"
                            />
                          </label>
                          <label className="block sm:col-span-2">
                            <span className="fa-kv-label mb-1 block">
                              参数 args（每行一个）
                            </span>
                            <textarea
                              value={s.argsText}
                              onChange={(e) =>
                                patchServer(s.localId, { argsText: e.target.value })
                              }
                              rows={3}
                              className="fa-input resize-none font-mono text-sm"
                              placeholder={
                                '-y\n@modelcontextprotocol/server-filesystem\n/path'
                              }
                            />
                          </label>
                        </div>
                      )}

                      {s.transport === 'sse' && (
                        <div className="mt-4 border-neutral-100 border-t pt-4">
                          <label className="block">
                            <span className="fa-kv-label mb-1 block">SSE URL</span>
                            <input
                              type="url"
                              value={s.url}
                              onChange={(e) =>
                                patchServer(s.localId, { url: e.target.value })
                              }
                              className="fa-input py-2 font-mono text-sm"
                              placeholder="https://example.com/mcp/sse"
                              autoComplete="off"
                            />
                          </label>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </details>
            </li>
          )
        })}
      </ul>

      <button type="button" onClick={addServer} className="fa-btn-secondary w-full sm:w-auto">
        + 添加 MCP 服务
      </button>
    </div>
  )
}
