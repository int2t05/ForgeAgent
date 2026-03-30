/**
 * 对话页左侧：会话列表、重命名（PATCH）、删除入口（与重命名并排）、新会话。
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createSession, getSessions, patchSession } from '@/api/sessions'
import { useSessionStore } from '@/stores/sessionStore'
import { formatRelativeTime } from '@/lib/format'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'

export interface SessionListPanelProps {
  /** 当前选中会话有尚未结束的任务时，禁止删除该条。 */
  currentSessionHasRunningTask: boolean
  /** 请求删除指定会话（由父级弹窗确认后再调 API）。 */
  onRequestDeleteSession: (sessionId: string) => void
  deleteSessionPending: boolean
}

function IconPencil({ className }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L8 18l-4 1 1-4L16.5 3.5z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconTrash({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function SessionListPanel({
  currentSessionHasRunningTask,
  onRequestDeleteSession,
  deleteSessionPending,
}: SessionListPanelProps) {
  const queryClient = useQueryClient()
  const sessionId = useSessionStore((s) => s.sessionId)
  const setSessionId = useSessionStore((s) => s.setSessionId)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [titleDraft, setTitleDraft] = useState('')

  const listQuery = useQuery({
    queryKey: ['sessions', 'list'],
    queryFn: () => getSessions({ limit: 100 }),
  })

  const createMutation = useMutation({
    mutationFn: () => createSession(),
    onSuccess: (res) => {
      setSessionId(res.session_id)
      setEditingId(null)
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
    },
  })

  const patchTitleMutation = useMutation({
    mutationFn: (payload: { id: string; title: string | null }) =>
      patchSession(payload.id, { title: payload.title }),
    onSuccess: (_data, vars) => {
      setEditingId(null)
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['session', vars.id, 'detail'] })
    },
  })

  const items = listQuery.data?.items ?? []

  function startRename(s: { id: string; title: string | null }) {
    setEditingId(s.id)
    setTitleDraft(s.title?.trim() ?? '')
  }

  function cancelRename() {
    setEditingId(null)
    setTitleDraft('')
  }

  function saveRename(sid: string) {
    const t = titleDraft.trim()
    patchTitleMutation.mutate({ id: sid, title: t || null })
  }

  return (
    <aside className="flex min-h-0 w-[min(17.5rem,88vw)] shrink-0 flex-col border-neutral-200/80 border-r bg-neutral-50/95">
      <div className="border-neutral-200/70 border-b px-3 py-3.5">
        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary-600 py-2.5 font-medium text-base text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
        >
          {createMutation.isPending ? '创建中…' : '+ 新对话'}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        {listQuery.isLoading && (
          <div className="flex justify-center py-10">
            <LoadingSpinner />
          </div>
        )}

        {listQuery.error && (
          <p className="px-2 py-4 text-center text-red-600 text-xs leading-relaxed">
            {listQuery.error instanceof Error ? listQuery.error.message : '无法加载会话'}
          </p>
        )}

        {patchTitleMutation.error && (
          <p className="mb-2 rounded-lg bg-red-50 px-2 py-2 text-red-700 text-xs">
            {patchTitleMutation.error instanceof Error
              ? patchTitleMutation.error.message
              : '重命名失败'}
          </p>
        )}

        {!listQuery.isLoading && !listQuery.error && items.length === 0 && (
          <p className="px-3 py-10 text-center text-base text-neutral-400 leading-relaxed">
            暂无会话，点击上方新建后与 Agent 对话
          </p>
        )}

        {!listQuery.isLoading && !listQuery.error && items.length > 0 && (
          <p className="fa-text-caption mb-2 px-2 font-medium text-neutral-400 uppercase tracking-[0.12em]">
            历史对话
          </p>
        )}

        <ul className="space-y-1">
          {items.map((s) => {
            const active = s.id === sessionId
            const isEditing = editingId === s.id
            const label = s.title?.trim() || '未命名会话'

            if (isEditing) {
              return (
                <li key={s.id} className="rounded-xl border border-primary-200/70 bg-primary-50/60 p-2">
                  <input
                    value={titleDraft}
                    onChange={(e) => setTitleDraft(e.target.value)}
                    className="fa-input mb-2 py-2"
                    placeholder="会话标题"
                    disabled={patchTitleMutation.isPending}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveRename(s.id)
                      if (e.key === 'Escape') cancelRename()
                    }}
                  />
                  <div className="flex justify-end gap-1.5">
                    <button
                      type="button"
                      className="rounded-lg px-2 py-1 text-neutral-600 text-xs hover:bg-white/80"
                      disabled={patchTitleMutation.isPending}
                      onClick={cancelRename}
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      className="rounded-lg bg-primary-600 px-2.5 py-1 text-white text-xs shadow-sm hover:bg-primary-700 disabled:opacity-50"
                      disabled={patchTitleMutation.isPending}
                      onClick={() => saveRename(s.id)}
                    >
                      保存
                    </button>
                  </div>
                </li>
              )
            }

            const deleteDisabled =
              deleteSessionPending ||
              (active && currentSessionHasRunningTask)

            return (
              <li key={s.id}>
                <div
                  className={`group flex items-stretch rounded-xl transition-colors ${
                    active
                      ? 'bg-primary-100/90 text-primary-900 ring-1 ring-primary-200/60'
                      : 'text-neutral-800 hover:bg-neutral-100/90'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSessionId(s.id)}
                    className="min-w-0 flex-1 px-3 py-2.5 text-left"
                  >
                    <span className="block truncate font-medium text-base">{label}</span>
                    <span
                      className={`fa-text-caption mt-0.5 block ${
                        active ? 'text-primary-700/80' : 'text-neutral-400'
                      }`}
                    >
                      {formatRelativeTime(s.created_at)}
                    </span>
                  </button>
                  <div
                    className={`flex shrink-0 flex-col justify-center border-l sm:flex-row ${
                      active
                        ? 'border-primary-200/50 divide-primary-100 divide-y sm:divide-x sm:divide-y-0'
                        : 'border-transparent opacity-0 divide-neutral-200/80 divide-y group-hover:border-neutral-200/60 group-hover:opacity-100 sm:divide-x sm:divide-y-0'
                    }`}
                  >
                    <button
                      type="button"
                      title="重命名"
                      disabled={patchTitleMutation.isPending}
                      onClick={(e) => {
                        e.stopPropagation()
                        startRename(s)
                      }}
                      className={`flex items-center justify-center px-2.5 py-2 transition sm:px-2 ${
                        active
                          ? 'text-primary-800 hover:bg-primary-200/50 disabled:opacity-40'
                          : 'text-neutral-500 hover:bg-neutral-200/80 disabled:opacity-40'
                      }`}
                    >
                      <IconPencil className="shrink-0" />
                    </button>
                    <button
                      type="button"
                      title={
                        active && currentSessionHasRunningTask
                          ? '当前会话有任务进行中，请结束后再删'
                          : '删除此会话'
                      }
                      aria-label={
                        active && currentSessionHasRunningTask
                          ? '当前会话有任务进行中，无法删除'
                          : '删除此会话'
                      }
                      disabled={deleteDisabled}
                      onClick={(e) => {
                        e.stopPropagation()
                        onRequestDeleteSession(s.id)
                      }}
                      className={`flex min-h-[2.5rem] min-w-[2.5rem] items-center justify-center px-2 py-2 transition sm:min-w-0 ${
                        active
                          ? 'text-red-600 hover:bg-red-100/70 disabled:cursor-not-allowed disabled:opacity-40'
                          : 'text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40'
                      }`}
                    >
                      <IconTrash className="shrink-0" />
                    </button>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </aside>
  )
}
