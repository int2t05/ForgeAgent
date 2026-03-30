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
  { value: 'mock', label: 'Mock' },
  { value: 'stdio', label: 'Stdio' },
  { value: 'sse', label: 'SSE' },
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
      <details className="group/full fa-card border-neutral-200/85 overflow-hidden open:shadow-sm">
        <summary className="cursor-pointer list-none px-4 py-2.5 font-medium text-base text-neutral-800 [&::-webkit-details-marker]:hidden">
          <span className="mr-2 inline-block text-neutral-400 transition-transform group-open/full:rotate-90">
            ▸
          </span>
          完整 JSON
        </summary>
        <div className="space-y-2 border-neutral-100 border-t px-4 py-3">
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
            className="fa-input max-h-[min(360px,50vh)] w-full resize-y font-mono leading-relaxed"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="fa-btn-secondary text-xs"
              onClick={applyFullMcpJson}
            >
              应用到列表
            </button>
            <button
              type="button"
              className="rounded px-2 py-1 text-neutral-600 text-xs hover:bg-neutral-100 hover:text-neutral-900"
              onClick={() => {
                setFullMcpText(canonicalFullJson)
                setFullMcpError(null)
              }}
            >
              重置文本
            </button>
          </div>
          {fullMcpError && (
            <p className="text-red-600 text-xs">{fullMcpError}</p>
          )}
        </div>
      </details>

      <div className="fa-card border-neutral-200/85 p-3">
        <p className="mb-2 text-base font-medium text-neutral-800">粘贴导入</p>
        <textarea
          value={importPaste}
          onChange={(e) => setImportPaste(e.target.value)}
          rows={5}
          spellCheck={false}
          className="fa-input mb-2 max-h-40 w-full resize-y font-mono"
          placeholder={`{\n  "mcpServers": {\n    "filesystem": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]\n    }\n  }\n}`}
        />
        <button
          type="button"
          className="fa-btn-secondary text-xs"
          onClick={applyPastedJson}
        >
          导入
        </button>
      </div>

      {importError && (
        <p className="text-red-600 text-xs leading-relaxed">{importError}</p>
      )}

      {servers.length === 0 && (
        <div className="fa-card border-dashed border-neutral-300/80 bg-neutral-50/50 px-4 py-6 text-center text-base text-neutral-500">
          暂无条目
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
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-base [&::-webkit-details-marker]:hidden">
                  <span className="text-neutral-400 select-none transition-transform group-open:rotate-90">
                    ▸
                  </span>
                  <span className="font-medium text-neutral-900">{title}</span>
                  <code className="fa-text-caption rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-neutral-600">
                    {s.transport}
                  </code>
                  {!s.enabled && (
                    <span className="fa-text-caption rounded bg-neutral-200/80 px-1.5 py-0.5 text-neutral-600">
                      已禁用
                    </span>
                  )}
                  <span className="fa-text-caption ml-auto font-display text-neutral-400 tabular-nums">
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
                      删除
                    </button>
                  </div>

                  {mode === 'json' ? (
                    <div className="space-y-2">
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
                        className="fa-input max-h-[min(320px,40vh)] w-full resize-y font-mono leading-relaxed"
                      />
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="fa-btn-secondary text-xs"
                          onClick={() => applyServerJson(s.localId)}
                        >
                          应用
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
                          重置
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
                          <span className="fa-kv-label mb-1 block">名称</span>
                          <input
                            type="text"
                            value={s.name}
                            onChange={(e) =>
                              patchServer(s.localId, { name: e.target.value })
                            }
                            className="fa-input py-2"
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
                          <span className="text-base text-neutral-700">启用</span>
                        </label>

                        <label className="block sm:col-span-2">
                          <span className="fa-kv-label mb-1 block">传输</span>
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
                            <span className="fa-section-title !mb-0">工具</span>
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
                                  <summary className="cursor-pointer list-none px-3 py-2 text-base [&::-webkit-details-marker]:hidden">
                                    <span className="mr-2 inline-block text-neutral-400 transition-transform group-open/tool:rotate-90">
                                      ▸
                                    </span>
                                    <code className="font-mono text-base">
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
                                        <span className="fa-kv-label mb-1 block">工具名</span>
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
                                        <span className="text-neutral-600 text-xs">只读</span>
                                      </label>
                                      <label className="block sm:col-span-2">
                                        <span className="fa-kv-label mb-1 block">描述</span>
                                        <input
                                          type="text"
                                          value={t.description}
                                          onChange={(e) =>
                                            patchTool(s.localId, ti, {
                                              description: e.target.value,
                                            })
                                          }
                                          className="fa-input py-2"
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
                              className="fa-input py-2 font-mono"
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
                              className="fa-input resize-none font-mono"
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
                              className="fa-input py-2 font-mono"
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
        + MCP
      </button>
    </div>
  )
}
