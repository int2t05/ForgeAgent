/**
 * 历史会话管理（记忆）：全屏列表，标题下双行消息预览，风格参考常见对话产品。
 */

import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import { errDetail } from '@/core/lib/errDetail'
import { sessionListSnippetText } from '@/core/lib/sessionListSnippet'
import { getSessions, patchSession, deleteSession } from '@/modules/sessions/api/sessions'
import { useSessionStore } from '@/modules/sessions/stores/sessionStore'
import { useSession } from '@/modules/sessions/hooks/useSession'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
} from '@/modules/tasks/hooks/usePendingComposerTask'
import { useComposerTaskStore } from '@/modules/tasks/stores/composerTaskStore'
import { ConfirmDialog } from '@/modules/shell/components/common/ConfirmDialog'
import { ErrorAlert } from '@/modules/shell/components/common/ErrorAlert'
import { LoadingSpinner } from '@/modules/shell/components/common/LoadingSpinner'
import type { SessionSummary } from '@/modules/sessions/types/session'

const MS_DAY = 86_400_000

function bucketIndex(createdAtIso: string): number {
  const t = new Date(createdAtIso).getTime()
  const age = Date.now() - t
  if (age <= 7 * MS_DAY) return 0
  if (age <= 30 * MS_DAY) return 1
  if (age <= 365 * MS_DAY) return 2
  return 3
}

const BUCKET_LABELS = ['近 7 天', '近 30 天', '近一年', '更早'] as const

function groupSessions(items: SessionSummary[]): { label: string; items: SessionSummary[] }[] {
  const buckets: SessionSummary[][] = [[], [], [], []]
  for (const s of items) {
    buckets[bucketIndex(s.created_at)]!.push(s)
  }
  return BUCKET_LABELS.map((label, i) => ({
    label,
    items: buckets[i]!,
  })).filter((g) => g.items.length > 0)
}

function IconEllipsis({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <circle cx="6" cy="12" r="1.65" />
      <circle cx="12" cy="12" r="1.65" />
      <circle cx="18" cy="12" r="1.65" />
    </svg>
  )
}

export function SessionHistoryPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { clearSession } = useSession()
  const sessionId = useSessionStore((s) => s.sessionId)
  const setSessionId = useSessionStore((s) => s.setSessionId)
  const busy = usePendingComposerTaskBusy()
  const { pendingSessionId } = usePendingComposerTaskMeta()

  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [titleDraft, setTitleDraft] = useState('')
  const renameShellRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

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

  const deleteSessionMutation = useMutation({
    mutationFn: (sid: string) => deleteSession(sid),
    onSuccess: (_data, sid) => {
      setConfirmDeleteId(null)
      setMenuOpenId(null)
      useComposerTaskStore.getState().clearStickyPlanForSession(sid)
      void queryClient.removeQueries({ queryKey: ['session', sid, 'messages'] })
      void queryClient.removeQueries({ queryKey: ['session', sid, 'detail'] })
      void queryClient.removeQueries({ queryKey: ['tasks', 'session', sid] })
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      if (sid === useSessionStore.getState().sessionId) clearSession()
    },
  })

  useEffect(() => {
    if (!editingId && !menuOpenId) return
    const onDocDown = (ev: MouseEvent) => {
      const t = ev.target
      if (!(t instanceof Node)) return
      if (renameShellRef.current?.contains(t)) return
      if (menuRef.current?.contains(t)) return
      setEditingId(null)
      setTitleDraft('')
      setMenuOpenId(null)
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [editingId, menuOpenId])

  const items = listQuery.data?.items ?? []
  const groups = groupSessions(items)

  function startRename(s: SessionSummary) {
    setMenuOpenId(null)
    setEditingId(s.id)
    setTitleDraft(s.title?.trim() ?? '')
  }

  function saveRename(sid: string) {
    const t = titleDraft.trim()
    patchTitleMutation.mutate({ id: sid, title: t || null })
  }

  function openSession(sid: string) {
    setSessionId(sid)
    navigate('/')
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-white">
      <ConfirmDialog
        open={confirmDeleteId != null}
        title="删除会话"
        description="将删除本会话下的全部消息与任务记录，且无法恢复。若仍有任务在执行，将无法删除。"
        confirmLabel="删除会话"
        pending={deleteSessionMutation.isPending}
        onCancel={() =>
          !deleteSessionMutation.isPending && setConfirmDeleteId(null)
        }
        onConfirm={() => {
          if (confirmDeleteId) deleteSessionMutation.mutate(confirmDeleteId)
        }}
      />

      <header className="shrink-0 border-neutral-200 border-b px-4 py-4 sm:px-6">
        <h1 className="mx-auto max-w-2xl text-center font-semibold text-base text-neutral-900 sm:text-lg">
          管理历史对话
        </h1>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-4 py-6 sm:px-6">
          {(listQuery.error || patchTitleMutation.error || deleteSessionMutation.error) && (
            <div className="mb-4 space-y-2">
              {listQuery.error ? (
                <ErrorAlert message="加载会话失败" detail={errDetail(listQuery.error)} />
              ) : null}
              {patchTitleMutation.error ? (
                <ErrorAlert message="重命名失败" detail={errDetail(patchTitleMutation.error)} />
              ) : null}
              {deleteSessionMutation.error ? (
                <ErrorAlert
                  message="删除会话失败"
                  detail={errDetail(deleteSessionMutation.error)}
                />
              ) : null}
            </div>
          )}

          {listQuery.isLoading && (
            <div className="flex justify-center py-16">
              <LoadingSpinner />
            </div>
          )}

          {!listQuery.isLoading && !listQuery.error && items.length === 0 && (
            <p className="py-12 text-center text-neutral-500 text-sm leading-relaxed">
              暂无会话，返回
              <Link to="/" className="text-primary-700 hover:underline">
                对话
              </Link>
              新建。
            </p>
          )}

          {items.length > 0
            ? groups.map((g) => (
                <section key={g.label} className="mb-8 last:mb-0">
                  <h2 className="mb-3 px-0.5 text-neutral-400 text-xs font-medium tracking-wide">
                    {g.label}
                  </h2>
                  <ul className="divide-y divide-neutral-100">
                    {g.items.map((s) => {
                  const label = s.title?.trim() || '未命名会话'
                  const snippet = sessionListSnippetText(s.last_message_preview)
                  const isEditing = editingId === s.id
                  const active = s.id === sessionId
                  const deleteDisabled =
                    deleteSessionMutation.isPending ||
                    (active && busy && sessionId === pendingSessionId)

                      if (isEditing) {
                        return (
                          <li key={s.id} className="py-4">
                            <div
                              ref={renameShellRef}
                              className="rounded-lg bg-neutral-50 px-3 py-2 ring-1 ring-neutral-200/80"
                            >
                              <input
                                value={titleDraft}
                                onChange={(e) => setTitleDraft(e.target.value)}
                                className="w-full border-0 bg-transparent py-1 text-base text-neutral-900 outline-none focus:ring-0"
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

                      return (
                        <li key={s.id} className="py-4">
                          <div className="flex gap-1 sm:gap-2">
                            <div className="min-w-0 flex-1">
                              <button
                                type="button"
                                onClick={() => openSession(s.id)}
                                onDoubleClick={(e) => {
                                  e.preventDefault()
                                  startRename(s)
                                }}
                                className="w-full text-left"
                                title="单击进入 · 双击改标题"
                              >
                                <span className="block text-[15px] text-blue-600 leading-snug hover:underline">
                                  {label}
                                </span>
                                <p
                                  className="mt-1 line-clamp-2 break-words text-[13px] leading-[1.45] text-[#666666]"
                                  title={
                                    snippet === '打开对话' ? undefined : snippet
                                  }
                                >
                                  {snippet}
                                </p>
                              </button>
                            </div>

                            <div
                              className="relative shrink-0 pt-0.5"
                              ref={menuOpenId === s.id ? menuRef : undefined}
                            >
                              <button
                                type="button"
                                aria-label="更多操作"
                                aria-expanded={menuOpenId === s.id}
                                onClick={() =>
                                  setMenuOpenId((id) => (id === s.id ? null : s.id))
                                }
                                className="rounded-md p-1 text-neutral-400 transition hover:bg-neutral-100 hover:text-neutral-600"
                              >
                                <IconEllipsis className="block" />
                              </button>
                              {menuOpenId === s.id ? (
                                <div className="absolute right-0 z-10 mt-1 min-w-[7.5rem] rounded-lg border border-neutral-200/80 bg-white py-1 shadow-lg">
                                  <button
                                    type="button"
                                    className="block w-full px-3 py-2 text-left text-neutral-800 text-sm hover:bg-neutral-50"
                                    disabled={patchTitleMutation.isPending}
                                    onClick={() => startRename(s)}
                                  >
                                    重命名
                                  </button>
                                  <button
                                    type="button"
                                    className="block w-full px-3 py-2 text-left text-red-600 text-sm hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                                    disabled={deleteDisabled}
                                    title={
                                      active && busy && sessionId === pendingSessionId
                                        ? '当前会话有任务进行中'
                                        : undefined
                                    }
                                    onClick={() => {
                                      setMenuOpenId(null)
                                      setConfirmDeleteId(s.id)
                                    }}
                                  >
                                    删除
                                  </button>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              ))
            : null}
        </div>
      </div>
    </div>
  )
}
