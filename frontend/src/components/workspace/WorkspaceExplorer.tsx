/**
 * 单层工作区浏览器：表头 + 文件夹/文件行；文件夹可进入、路径可复制。
 */

import { CopyTextButton } from '@/components/common/CopyTextButton'
import type { WorkspaceSnapshotResponse } from '@/types/workspace'

/** 将字节数格式化为 B / KB / MB / GB 展示串。 */
function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export interface WorkspaceExplorerProps {
  /** 当前层级的接口快照 */
  data: WorkspaceSnapshotResponse
  onOpenDirectory: (absolutePath: string) => void
  onGoUp: () => void
  onGoRoot: () => void
}

/** 纯展示 + 导航回调；数据与请求由父组件负责。 */
export function WorkspaceExplorer({
  data,
  onOpenDirectory,
  onGoUp,
  onGoRoot,
}: WorkspaceExplorerProps) {
  const canGoUp = data.parent_path != null && data.parent_path !== ''

  return (
    <div className="space-y-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={!canGoUp}
          onClick={() => onGoUp()}
          className="rounded-md border border-neutral-200 bg-white px-2 py-1 font-medium text-neutral-700 hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          ↑ 上级
        </button>
        <button
          type="button"
          onClick={() => onGoRoot()}
          className="rounded-md border border-neutral-200 bg-white px-2 py-1 font-medium text-neutral-700 hover:bg-neutral-50"
        >
          工作区根
        </button>
      </div>

      <div>
        <p className="font-medium text-neutral-600">当前位置（绝对路径）</p>
        <div className="mt-1 flex flex-wrap items-start gap-2">
          <pre className="max-h-28 min-w-0 flex-1 overflow-auto rounded-md bg-neutral-900/90 p-2 font-mono text-[11px] text-neutral-100 leading-snug">
            {data.current_path}
          </pre>
          <CopyTextButton text={data.current_path} label="复制路径" />
        </div>
      </div>

      <div>
        <div className="rounded-md border border-neutral-200 bg-neutral-100/80 px-2 py-1.5 font-medium text-[11px] text-neutral-600">
          <span className="inline-block w-[min(55%,14rem)] pr-2">名称</span>
          <span className="inline-block w-14 shrink-0">类型</span>
          <span className="inline-block">大小</span>
        </div>
        <ul className="max-h-[min(50vh,22rem)] overflow-auto rounded-md border border-t-0 border-neutral-200 bg-white py-0.5">
          {data.workspace_listing.length === 0 ? (
            <li className="px-2 py-2 text-neutral-500">此文件夹为空</li>
          ) : (
            data.workspace_listing.map((ent) => (
              <li
                key={`${ent.path}-${ent.name}`}
                className="flex flex-wrap items-center gap-x-2 border-neutral-100 border-b px-2 py-1.5 text-[11px] last:border-b-0 sm:flex-nowrap"
              >
                <div className="min-w-0 flex-[1_1_55%] sm:max-w-[14rem]">
                  {ent.is_dir ? (
                    <button
                      type="button"
                      onClick={() => onOpenDirectory(ent.path)}
                      className="w-full text-left font-mono text-primary-800 leading-snug underline decoration-primary-300 decoration-dotted underline-offset-2 hover:text-primary-950 [overflow-wrap:anywhere]"
                    >
                      <span className="mr-1 opacity-80" aria-hidden>
                        📁
                      </span>
                      {ent.name}
                    </button>
                  ) : (
                    <span className="block font-mono text-neutral-800 leading-snug [overflow-wrap:anywhere]">
                      <span className="mr-1 opacity-70" aria-hidden>
                        📄
                      </span>
                      {ent.name}
                    </span>
                  )}
                </div>
                <span className="w-14 shrink-0 text-neutral-600">
                  {ent.is_dir ? '文件夹' : '文件'}
                </span>
                <span className="min-w-0 shrink-0 font-mono text-neutral-600">
                  {ent.is_dir ? '—' : formatFileSize(ent.size_bytes ?? null)}
                </span>
                <div className="ml-auto shrink-0">
                  <CopyTextButton text={ent.path} label="复制" />
                </div>
              </li>
            ))
          )}
        </ul>
        {data.workspace_listing_truncated ? (
          <p className="mt-1 text-amber-900/90">
            本文件夹仅展示前 200 项；可进入子目录继续浏览。
          </p>
        ) : null}
      </div>
    </div>
  )
}
