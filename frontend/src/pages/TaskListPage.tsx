/**
 * 任务列表页：全部任务、状态筛选、分页。
 */

import { useState } from 'react'
import { Link } from 'react-router'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { EmptyState } from '@/components/common/EmptyState'
import { useTasks } from '@/hooks/useTasks'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP, DEFAULT_PAGE_SIZE } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import type { TaskStatus } from '@/types/task'

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '执行中' },
  { value: 'success', label: '已完成' },
  { value: 'failed', label: '已失败' },
  { value: 'cancelled', label: '已取消' },
]

export function TaskListPage() {
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(0)

  const offset = page * DEFAULT_PAGE_SIZE
  const { data, isLoading, error } = useTasks({
    limit: DEFAULT_PAGE_SIZE,
    offset,
    status: statusFilter || undefined,
  })

  const totalPages = data ? Math.ceil(data.total / DEFAULT_PAGE_SIZE) : 0

  return (
    <div className="flex flex-1 flex-col">
      <Header title="任务列表" />

      <div className="flex flex-1 flex-col gap-4 px-6 py-6">
        {/* 筛选栏 */}
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(0)
            }}
            className="fa-select"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {data && (
            <span className="text-neutral-500 text-sm tabular-nums">共 {data.total} 条</span>
          )}
        </div>

        {/* 内容区 */}
        {isLoading && <LoadingSpinner />}

        {error && (
          <ErrorAlert
            message="加载任务列表失败"
            detail={error instanceof Error ? error.message : '未知错误'}
          />
        )}

        {data && data.items.length === 0 && (
          <EmptyState
            title="暂无任务"
            description="可在首页创建第一个任务"
            action={
              <Link to="/" className="fa-link text-sm">
                返回首页
              </Link>
            }
          />
        )}

        {data && data.items.length > 0 && (
          <div className="fa-card overflow-hidden rounded-lg p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-neutral-200 border-b bg-neutral-50/90">
                <tr className="text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">摘要</th>
                  <th className="px-4 py-3">会话 ID</th>
                  <th className="px-4 py-3">计划版本</th>
                  <th className="px-4 py-3">创建时间</th>
                  <th className="px-4 py-3">更新时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {data.items.map((task) => {
                  const colors =
                    STATUS_COLOR_MAP[task.status as TaskStatus] ??
                    STATUS_COLOR_MAP.pending
                  return (
                    <tr key={task.id} className="transition-colors hover:bg-neutral-50/80">
                      <td className="px-4 py-3">
                        <Link to={`/tasks/${task.id}`}>
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${colors.bg} ${colors.text}`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${colors.dot}`}
                            />
                            {STATUS_LABEL_MAP[task.status as TaskStatus] ?? task.status}
                          </span>
                        </Link>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-neutral-800">
                        <Link to={`/tasks/${task.id}`} className="hover:text-primary-600">
                          {task.summary ?? '(无摘要)'}
                        </Link>
                      </td>
                      <td className="max-w-[8.5rem] px-4 py-3">
                        <span
                          className="fa-kv-value-mono block truncate"
                          title={task.session_id}
                        >
                          {task.session_id}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-neutral-500 tabular-nums">
                        v{task.plan_version}
                      </td>
                      <td className="px-4 py-3 text-neutral-500">
                        {formatDateTime(task.created_at)}
                      </td>
                      <td className="px-4 py-3 text-neutral-500">
                        {formatDateTime(task.updated_at)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-2">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="fa-btn-secondary"
            >
              上一页
            </button>
            <span className="text-neutral-500 text-sm tabular-nums">
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="fa-btn-secondary"
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
