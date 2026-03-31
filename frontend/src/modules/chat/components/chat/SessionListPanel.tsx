/**
 * 全局侧栏「历史对话」：位于主导航下方；新会话由对话页顶栏操作。
 */

import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { getSessions, patchSession } from '@/modules/sessions/api/sessions'
import { useSessionStore } from '@/modules/sessions/stores/sessionStore'
import { LoadingSpinner } from '@/modules/shell/components/common/LoadingSpinner'

export interface SessionListPanelProps {
  currentSessionHasRunningTask: boolean
  onRequestDeleteSession: (sessionId: string) => void
  deleteSessionPending: boolean
}

function IconPencil({ className }: { className?: string }) {
  return (
    <svg className={className} width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden>
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
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
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
  const renameShellRef = useRef<HTMLDivElement>(null)

  const listQuery = useQuery({
    queryKey: ['sessions', 'list'],
    queryFn: () => getSessions({ limit: 100 }),
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

  useEffect(() => {
    if (!editingId) return
    const onDocDown = (ev: MouseEvent) => {
      const t = ev.target
      if (!(t instanceof Node)) return
      if (renameShellRef.current?.contains(t)) return
      setEditingId(null)
      setTitleDraft('')
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [editingId])

  const items = listQuery.data?.items ?? []

  function startRename(s: { id: string; title: string | null }) {
    setEditingId(s.id)
    setTitleDraft(s.title?.trim() ?? '')
  }

  function saveRename(sid: string) {
    const t = titleDraft.trim()
    patchTitleMutation.mutate({ id: sid, title: t || null })
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#f5f5f5]">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-neutral-200/70 border-t">
        <div className="shrink-0 px-2 pt-2">
          <Link
            to="/chat/history"
            className="fa-text-caption inline-block font-medium text-neutral-400 underline-offset-2 transition hover:text-neutral-600 hover:underline"
          >
            历史对话
          </Link>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-1.5 pb-2 pt-1.5 [-webkit-overflow-scrolling:touch]">
          {listQuery.isLoading && (
            <div className="flex justify-center py-6">
              <LoadingSpinner />
            </div>
          )}

          {listQuery.error && (
            <p className="px-1 py-2 text-center text-red-600 text-xs leading-relaxed">
              {listQuery.error instanceof Error ? listQuery.error.message : '无法加载会话'}
            </p>
          )}

          {patchTitleMutation.error && (
            <p className="mb-1 rounded-md bg-red-50 px-1.5 py-1 text-red-700 text-xs">
              {patchTitleMutation.error instanceof Error
                ? patchTitleMutation.error.message
                : '重命名失败'}
            </p>
          )}

          {!listQuery.isLoading && !listQuery.error && items.length === 0 && (
            <p className="px-1 py-4 text-center text-neutral-500 text-xs leading-relaxed">
              暂无会话，请在对话题栏点击「新会话」
            </p>
          )}

          <ul className="space-y-0.5">
            {items.map((s) => {
              const active = s.id === sessionId
              const isEditing = editingId === s.id
              const label = s.title?.trim() || '未命名会话'

              if (isEditing) {
                return (
                  <li key={s.id} className="px-0.5">
                    <div
                      ref={renameShellRef}
                      className="rounded-lg bg-white px-2 py-1 shadow-sm ring-1 ring-neutral-200/80"
                    >
                      <input
                        value={titleDraft}
                        onChange={(e) => setTitleDraft(e.target.value)}
                        className="w-full border-0 bg-transparent py-0.5 text-base text-neutral-900 outline-none focus:ring-0"
                        placeholder="会话标题"
                        disabled={patchTitleMutation.isPending}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveRename(s.id)
                          if (e.key === 'Escape') {
                            setEditingId(null)
                            setTitleDraft('')
                          }
                        }}
                      />
                    </div>
                  </li>
                )
              }

              const deleteDisabled =
                deleteSessionPending || (active && currentSessionHasRunningTask)

              return (
                <li key={s.id} className="px-0.5">
                  <div
                    className={`group relative flex items-center gap-0.5 rounded-lg py-1 pl-2 pr-1 transition-colors ${
                      active
                        ? 'bg-white text-neutral-900 shadow-sm ring-1 ring-neutral-200/60'
                        : 'text-neutral-800 hover:bg-white/70'
                    }`}
                  >
                    <Link
                      to="/"
                      onClick={() => setSessionId(s.id)}
                      onDoubleClick={(e) => {
                        e.preventDefault()
                        startRename(s)
                      }}
                      className={`min-w-0 flex-1 truncate text-left text-base leading-tight no-underline ${
                        active ? 'font-bold text-neutral-900' : 'font-normal text-neutral-600'
                      }`}
                      title="单击切换 · 双击改标题"
                    >
                      {label}
                    </Link>

                    <div className="pointer-events-none flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
                      <button
                        type="button"
                        title="重命名"
                        disabled={patchTitleMutation.isPending}
                        onClick={(e) => {
                          e.stopPropagation()
                          startRename(s)
                        }}
                        className={`rounded p-1 transition ${active ? 'text-primary-600 hover:bg-neutral-100' : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800'} disabled:opacity-40`}
                      >
                        <IconPencil className="shrink-0" />
                      </button>
                      <button
                        type="button"
                        title={
                          active && currentSessionHasRunningTask
                            ? '当前会话有任务进行中'
                            : '删除'
                        }
                        aria-label="删除会话"
                        disabled={deleteDisabled}
                        onClick={(e) => {
                          e.stopPropagation()
                          onRequestDeleteSession(s.id)
                        }}
                        className="rounded p-1 text-red-500 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-35"
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
      </div>
    </div>
  )
}
