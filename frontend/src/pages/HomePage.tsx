/**
 * 首页 / 仪表盘：最近任务列表 + 发起任务表单。
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
import { createTask } from '@/api/tasks'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP } from '@/lib/constants'
import { formatRelativeTime } from '@/lib/format'

export function HomePage() {
  const navigate = useNavigate()
  const { sessionId } = useSession()
  const { data, isLoading, error } = useTasks({ limit: 5 })
  const [message, setMessage] = useState('')

  const submitMutation = useMutation({
    mutationFn: (userMessage: string) =>
      createTask({ session_id: sessionId!, user_message: userMessage }),
    onSuccess: (res) => {
      setMessage('')
      navigate(`/tasks/${res.task_id}`)
    },
  })

  /** 提交新任务。 */
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || !sessionId) return
    submitMutation.mutate(trimmed)
  }

  return (
    <div className="flex flex-1 flex-col">
      <Header title="首页" />

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-8">
        {/* 发起任务 */}
        <section>
          <h2 className="mb-3 text-sm font-medium text-neutral-700">发起任务</h2>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="描述你的任务…"
              rows={3}
              className="w-full resize-none rounded-lg border border-neutral-300 bg-white px-4 py-3 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
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
              disabled={!message.trim() || !sessionId || submitMutation.isPending}
              className="self-end rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitMutation.isPending ? '提交中…' : '提交'}
            </button>
          </form>
        </section>

        {/* 最近任务 */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-medium text-neutral-700">最近任务</h2>
            <Link to="/tasks" className="text-sm text-blue-600 hover:text-blue-700">
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
              description="在上方输入任务描述开始第一个任务"
            />
          )}

          {data && data.items.length > 0 && (
            <ul className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 bg-white">
              {data.items.map((task) => {
                const colors = STATUS_COLOR_MAP[task.status]
                return (
                  <li key={task.id}>
                    <Link
                      to={`/tasks/${task.id}`}
                      className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-neutral-50"
                    >
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${colors.bg} ${colors.text}`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${colors.dot}`} />
                        {STATUS_LABEL_MAP[task.status]}
                      </span>
                      <span className="flex-1 truncate text-sm text-neutral-800">
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
