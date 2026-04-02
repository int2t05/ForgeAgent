/**
 * 设置页：工具注册表只读展示（GET /api/v1/tools）。
 * 与 MCP / Skills 保存后的 invalidate 联动，可手动刷新。
 */

import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { refreshToolsRegistry } from '@/api/tools'
import { useTools } from '@/hooks/useTools'
import type { ToolInfo, ToolSource } from '@/types/tool'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'

const SOURCE_LABEL: Record<ToolSource, string> = {
  builtin: '内置',
  mcp: 'MCP',
}

const SOURCE_FILTER: Array<{ value: ToolSource | 'all'; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'builtin', label: '内置' },
  { value: 'mcp', label: 'MCP' },
]

/** 来源标签样式：中性底纹，强调色仅用于筛选项选中态与主按钮。 */
const SOURCE_BADGE_CLASS =
  'border border-neutral-200 bg-neutral-100 text-neutral-700'

function ToolRow({ tool }: { tool: ToolInfo }) {
  const hasSchema = tool.parameters != null

  return (
    <article className="fa-card border-neutral-200/90 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-sm text-neutral-900">
              {tool.name}
            </code>
            <span className={`rounded px-2 py-0.5 text-xs font-medium ${SOURCE_BADGE_CLASS}`}>
              {SOURCE_LABEL[tool.source]}
            </span>
            {tool.read_only === true && (
              <span className="rounded border border-neutral-200 bg-neutral-50 px-2 py-0.5 text-xs text-neutral-600">
                只读
              </span>
            )}
          </div>
          <p className="mt-2 text-base leading-relaxed text-neutral-700">
            {tool.description}
          </p>
        </div>
      </div>

      {hasSchema ? (
        <details className="mt-3 rounded-lg border border-neutral-200 bg-neutral-50/80">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-100/80">
            参数 JSON Schema
          </summary>
          <pre className="max-h-64 overflow-auto border-t border-neutral-200 bg-white p-3 font-mono text-sm leading-snug text-neutral-800">
            {JSON.stringify(tool.parameters, null, 2)}
          </pre>
        </details>
      ) : (
        <p className="fa-text-caption mt-3 text-neutral-500">无 parameters 定义</p>
      )}
    </article>
  )
}

interface McpToolGroup {
  serverName: string
  tools: ToolInfo[]
}

export function ToolsRegistrySection() {
  const queryClient = useQueryClient()
  const { data, isLoading, isFetching, error } = useTools()
  const [filter, setFilter] = useState<ToolSource | 'all'>('all')
  const [refreshing, setRefreshing] = useState(false)

  async function handleRefreshRegistry() {
    setRefreshing(true)
    try {
      const latest = await refreshToolsRegistry()
      queryClient.setQueryData(['tools'], latest)
    } finally {
      setRefreshing(false)
    }
  }

  const tools = data?.tools ?? []
  const sorted = useMemo(() => {
    const base = filter === 'all' ? tools : tools.filter((t) => t.source === filter)
    return [...base].sort((a, b) => {
      const bySource = a.source.localeCompare(b.source)
      return bySource !== 0 ? bySource : a.name.localeCompare(b.name)
    })
  }, [tools, filter])

  const mcpGroups = useMemo<McpToolGroup[]>(() => {
    const grouped = new Map<string, ToolInfo[]>()
    for (const tool of sorted) {
      if (tool.source !== 'mcp') continue
      const serverName = tool.mcp_server_name?.trim() || 'mcp'
      const bucket = grouped.get(serverName)
      if (bucket) {
        bucket.push(tool)
      } else {
        grouped.set(serverName, [tool])
      }
    }
    return [...grouped.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([serverName, tools]) => ({
        serverName,
        tools: [...tools].sort((a, b) => a.name.localeCompare(b.name)),
      }))
  }, [sorted])

  const nonMcpTools = useMemo(
    () => sorted.filter((tool) => tool.source !== 'mcp'),
    [sorted],
  )

  /** 是否仅有内置工具（此时「全部」与「内置」列表一致，避免误以为筛选失效）。 */
  const onlyBuiltin =
    tools.length > 0 && tools.every((t) => t.source === 'builtin')

  return (
    <section className="mb-4">
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-neutral-800">工具注册表</h2>
          <p className="mt-1 text-sm text-neutral-500">
            与执行阶段可用工具一致（只读）。保存 MCP / Skills 路径后会刷新；改环境变量（如 TAVILY_API_KEY）后请点「刷新列表」。Skills
            路径仅供规划步导入 SKILL.md，不出现在此列表。
          </p>
        </div>
        <button
          type="button"
          className="fa-btn-secondary shrink-0 self-start sm:self-auto"
          disabled={isFetching || refreshing}
          onClick={() => void handleRefreshRegistry()}
        >
          {isFetching || refreshing ? '刷新中…' : '刷新列表'}
        </button>
      </div>

      <fieldset className="relative z-10 mb-4 border-0 p-0">
        <legend className="sr-only">按工具来源筛选</legend>
        <div className="flex flex-wrap gap-2">
          {SOURCE_FILTER.map((opt) => {
            const count =
              opt.value === 'all'
                ? tools.length
                : tools.filter((t) => t.source === opt.value).length
            const inputId = `fa-tool-filter-${opt.value}`
            const selected =
              filter === opt.value
                ? 'border-primary-300 bg-primary-50 text-primary-800 font-medium'
                : 'border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-50'
            return (
              <label
                key={opt.value}
                htmlFor={inputId}
                className={`relative inline-flex cursor-pointer select-none rounded-full border px-3 py-1 text-sm transition-colors ${selected}`}
              >
                <input
                  id={inputId}
                  type="radio"
                  name="fa-tool-source-filter"
                  value={opt.value}
                  checked={filter === opt.value}
                  className="sr-only"
                  onChange={() => setFilter(opt.value)}
                />
                {opt.label}
                <span className="ml-1 tabular-nums text-neutral-400">({count})</span>
              </label>
            )
          })}
        </div>
      </fieldset>

      {onlyBuiltin && (filter === 'all' || filter === 'builtin') && (
        <p className="mb-3 text-sm text-neutral-500">
          当前仅有内置工具，「全部」与「内置」列表相同。需要 MCP 来源时请在上方配置并保存。
        </p>
      )}

      {error && (
        <ErrorAlert
          message="加载工具列表失败"
          detail={error instanceof Error ? error.message : undefined}
        />
      )}

      {isLoading && !data && (
        <div className="py-8">
          <LoadingSpinner />
        </div>
      )}

      {!isLoading && !error && sorted.length === 0 && (
        <p className="rounded-lg border border-dashed border-neutral-200 bg-neutral-50/50 px-4 py-8 text-center text-base text-neutral-600">
          {filter === 'mcp'
            ? '暂无 MCP 来源工具（请到页面上方添加 MCP 并保存，再点「刷新列表」）。'
            : '当前筛选下暂无工具。'}
        </p>
      )}

      {!error && sorted.length > 0 && (
        <div className="space-y-3">
          {mcpGroups.map((group) => (
            <details
              key={`mcp-group:${group.serverName}`}
              className="fa-card border-neutral-200/90 overflow-hidden"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-neutral-500 select-none">▸</span>
                  <span className="font-medium text-neutral-900">
                    MCP · <code className="font-mono text-sm">{group.serverName}</code>
                  </span>
                </div>
                <span className="fa-text-caption tabular-nums text-neutral-500">
                  {group.tools.length} tools
                </span>
              </summary>
              <ul className="space-y-3 border-t border-neutral-200 bg-neutral-50/40 p-3">
                {group.tools.map((tool) => (
                  <li key={`mcp:${group.serverName}:${tool.name}`}>
                    <ToolRow tool={tool} />
                  </li>
                ))}
              </ul>
            </details>
          ))}

          {nonMcpTools.length > 0 && (
            <ul className="flex flex-col gap-3">
              {nonMcpTools.map((tool) => (
                <li key={`${tool.source}:${tool.name}`}>
                  <ToolRow tool={tool} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!error && !isLoading && tools.length > 0 && (
        <p className="fa-text-caption mt-4 text-neutral-500">
          共 {tools.length} 个工具
          {filter !== 'all' ? `（当前显示 ${sorted.length} 个）` : ''}
        </p>
      )}
    </section>
  )
}
