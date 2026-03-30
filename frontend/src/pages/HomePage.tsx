/**
 * 概览：最近任务 + 快捷发起（无会话时自动创建后再提交）。
 */

import { useState } from 'react'
import { useNavigate, Link } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { EmptyState } from '@/components/common/EmptyState'
import { useTasks } from '@/hooks/useTasks'
import { useSession } from '@/hooks/useSession'
import { createSession } from '@/api/sessions'
import { createTask } from '@/api/tasks'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP } from '@/lib/constants'
import { formatRelativeTime } from '@/lib/format'

export function HomePage() {
  const navigate = useNavigate()
  const { sessionId, setSessionId } = useSession()
  const { data, isLoading, error } = useTasks({ limit: 5 })
  const [message, setMessage] = useState('')

  const submitMutation = useMutation({
    mutationFn: async (userMessage: string) => {
      let sid = sessionId
      if (!sid) {
        const created = await createSession()
        sid = created.session_id
        setSessionId(sid)
      }
      return createTask({ session_id: sid, user_message: userMessage })
    },
    onSuccess: (res) => {
      setMessage('')
      navigate(`/tasks/${res.task_id}`)
    },
  })

  /** 提交新任务。 */
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = message.trim()
    if (!trimmed) return
    submitMutation.mutate(trimmed)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <Header title="概览" />

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-8">
        {/* 发起任务 */}
        <section className="fa-reveal">
          <h2 className="fa-section-title">发起任务</h2>
          <form
            onSubmit={handleSubmit}
            className="fa-card flex flex-col gap-3 border-neutral-200/80 p-5"
          >
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="描述你的任务…"
              rows={3}
              className="fa-input resize-none"
            />
            {submitMutation.error && (
              <ErrorAlert
                message="任务创建失败"
                detail={
                  submitMutation.error instanceof Error
                    ? submitMutation.error.message
                    : '未知错误'
                }
              />
            )}
            <button
              type="submit"
              disabled={!message.trim() || submitMutation.isPending}
              className="fa-btn-primary self-end"
            >
              {submitMutation.isPending ? '提交中…' : '提交'}
            </button>
          </form>
        </section>

        {/* 最近任务 */}
        <section className="fa-reveal fa-reveal-delay-1">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="fa-section-title !mb-0">最近任务</h2>
            <Link to="/tasks" className="fa-link shrink-0 text-base">
              查看全部
            </Link>
          </div>

          {isLoading && <LoadingSpinner />}

          {error && (
            <ErrorAlert
              message="加载任务失败"
              detail={error instanceof Error ? error.message : '无法连接后端服务'}
            />
          )}

          {data && data.items.length === 0 && (
            <EmptyState
              title="暂无任务"
              description="在上方输入任务描述开始第一个任务，或通过左侧「对话」与 Agent 聊天"
            />
          )}

          {data && data.items.length > 0 && (
            <ul className="fa-card divide-y divide-neutral-100 overflow-hidden p-0">
              {data.items.map((task) => {
                const colors = STATUS_COLOR_MAP[task.status]
                return (
                  <li key={task.id}>
                    <Link
                      to={`/tasks/${task.id}`}
                      className="flex items-center gap-4 px-4 py-3 transition-[background-color] duration-200 hover:bg-neutral-50/90"
                    >
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${colors.bg} ${colors.text}`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${colors.dot}`} />
                        {STATUS_LABEL_MAP[task.status]}
                      </span>
                      <span className="flex-1 truncate text-base text-neutral-800">
                        {task.summary ?? '(无摘要)'}
                      </span>
                      <span className="shrink-0 text-xs text-neutral-400">
                        {formatRelativeTime(task.updated_at)}
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
