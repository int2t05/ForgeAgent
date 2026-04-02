/**
 * 对话页右侧工作区侧栏：按路径分页拉取列表；「刷新」触发表侧 reload_config 与工具注册表同步。
 */

import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getWorkspaceSnapshot } from '@/api/workspace'
import { WorkspaceExplorer } from '@/components/workspace/WorkspaceExplorer'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { errDetail } from '@/utils/errDetail'

export interface ChatWorkspaceSidebarProps {
  className?: string
}

/** 组合 TanStack Query（目录）与 Mutation（配置刷新），并向 WorkspaceExplorer 透传回调。 */
export function ChatWorkspaceSidebar({ className = '' }: ChatWorkspaceSidebarProps) {
  const queryClient = useQueryClient()
  // 1. 当前列举目录绝对路径；null 表示工作区根
  const [navPath, setNavPath] = useState<string | null>(null)

  // 2. 单层列表（不含 reload_config，避免每次展开都重建工具）
  const q = useQuery({
    queryKey: ['workspace', 'snapshot', navPath ?? 'ROOT'],
    queryFn: () =>
      getWorkspaceSnapshot(navPath != null && navPath !== '' ? { path: navPath } : {}),
    staleTime: 15_000,
  })

  // 3. 用户点「刷新」：服务端读库 + 重建工具，并回到根层缓存
  const reloadMut = useMutation({
    mutationFn: () => getWorkspaceSnapshot({ reloadConfig: true }),
    onSuccess: (data) => {
      setNavPath(null)
      queryClient.setQueryData(['workspace', 'snapshot', 'ROOT'], data)
    },
  })

  const onGoRoot = useCallback(() => {
    setNavPath(null)
  }, [])

  const onGoUp = useCallback(() => {
    const p = q.data?.parent_path
    if (p == null || p === '') {
      setNavPath(null)
    } else {
      setNavPath(p)
    }
  }, [q.data?.parent_path])

  const onOpenDirectory = useCallback((absolutePath: string) => {
    setNavPath(absolutePath)
  }, [])

  const busy = q.isFetching || reloadMut.isPending

  return (
    <aside
      className={`flex max-h-[min(40vh,26rem)] w-full shrink-0 flex-col border-neutral-200 border-t bg-white md:max-h-none md:w-80 md:border-l md:border-t-0 lg:w-[22rem] ${className}`}
      aria-label="Agent 工作区"
    >
      <div className="flex shrink-0 items-start justify-between gap-2 border-neutral-200 border-b px-3 py-2.5">
        <div className="min-w-0">
          <p className="font-medium text-neutral-800 text-sm">Agent 工作区</p>
          <p className="text-neutral-500 text-xs leading-snug">
            在设置中修改根目录后，点此「刷新」同步列表与文件工具
          </p>
        </div>
        <button
          type="button"
          className="shrink-0 rounded-md border border-primary-200 bg-primary-500/10 px-2 py-1 font-medium text-primary-900 text-xs hover:bg-primary-500/15 disabled:opacity-50"
          title="从数据库重读工作区根并重建工具注册表"
          onClick={() => reloadMut.mutate()}
          disabled={busy}
        >
          {reloadMut.isPending ? '…' : '刷新'}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {q.isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : null}
        {q.error ? (
          <ErrorAlert message="加载工作区失败" detail={errDetail(q.error)} />
        ) : null}
        {reloadMut.error ? (
          <ErrorAlert message="刷新配置失败" detail={errDetail(reloadMut.error)} />
        ) : null}
        {q.data ? (
          <WorkspaceExplorer
            data={q.data}
            onOpenDirectory={onOpenDirectory}
            onGoUp={onGoUp}
            onGoRoot={onGoRoot}
          />
        ) : null}
      </div>
    </aside>
  )
}
