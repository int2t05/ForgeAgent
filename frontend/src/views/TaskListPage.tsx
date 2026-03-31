/**
 * 任务列表页：全部任务、状态筛选、分页。
 */

import { useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Header } from '@/layouts/Header'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { EmptyState } from '@/components/ui/EmptyState'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useTasks } from '@/hooks/useTasks'
import { deleteTask, patchTask } from '@/api/tasks'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP, DEFAULT_PAGE_SIZE } from '@/constants/task'
import { formatDateTime } from '@/utils/format'
import type { TaskStatus, TaskSummary } from '@/types/task'

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '执行中' },
  { value: 'success', label: '已完成' },
  { value: 'failed', label: '已失败' },
  { value: 'cancelled', label: '已取消' },
]

export function TaskListPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(0)
  const [taskToDelete, setTaskToDelete] = useState<TaskSummary | null>(null)
  const [taskToCancel, setTaskToCancel] = useState<TaskSummary | null>(null)

  const offset = page * DEFAULT_PAGE_SIZE
  const { data, isLoading, error } = useTasks({
    limit: DEFAULT_PAGE_SIZE,
    offset,
    status: statusFilter || undefined,
  })

  const totalPages = data ? Math.ceil(data.total / DEFAULT_PAGE_SIZE) : 0

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      setTaskToDelete(null)
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => patchTask(taskId, { status: 'cancelled' }),
    onSuccess: () => {
      setTaskToCancel(null)
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <Header title="任务列表" />

      <ConfirmDialog
        open={taskToCancel != null}
        title="取消任务"
        description={
          taskToCancel
            ? '取消后 Agent 将停止写回成功结果，状态变为「已取消」。确定吗？'
            : ''
        }
        confirmLabel="取消任务"
        pending={cancelMutation.isPending}
        onCancel={() => !cancelMutation.isPending && setTaskToCancel(null)}
        onConfirm={() => {
          if (taskToCancel) cancelMutation.mutate(taskToCancel.id)
        }}
      />

      <ConfirmDialog
        open={taskToDelete != null}
        title="删除任务"
        description={
          taskToDelete
            ? `确定删除任务「${taskToDelete.summary?.slice(0, 80) || taskToDelete.id}」？此操作不可恢复。`
            : ''
        }
        confirmLabel="删除"
        pending={deleteMutation.isPending}
        onCancel={() => !deleteMutation.isPending && setTaskToDelete(null)}
        onConfirm={() => {
          if (taskToDelete) deleteMutation.mutate(taskToDelete.id)
        }}
      />

      <div className="flex flex-1 flex-col gap-4 px-6 py-6">
        {/* 筛选栏 */}
        <div className="fa-reveal fa-card flex flex-wrap items-center gap-3 border-neutral-200/85 p-4">
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
            <span className="text-base text-neutral-500 tabular-nums">共 {data.total} 条</span>
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

        {cancelMutation.error && (
          <ErrorAlert
            message="取消任务失败"
            detail={
              cancelMutation.error instanceof Error
                ? cancelMutation.error.message
                : '未知错误'
            }
          />
        )}

        {deleteMutation.error && (
          <ErrorAlert
            message="删除失败"
            detail={
              deleteMutation.error instanceof Error
                ? deleteMutation.error.message
                : '未知错误'
            }
          />
        )}

        {data && data.items.length === 0 && (
          <EmptyState
            title="暂无任务"
            description="可在「对话」或「概览」中创建任务"
            action={
              <Link to="/" className="fa-link text-base">
                前往对话
              </Link>
            }
          />
        )}

        {data && data.items.length > 0 && (
          <div className="fa-reveal fa-reveal-delay-1 fa-card overflow-hidden rounded-lg p-0">
            <div className="max-w-full overflow-x-auto [-webkit-overflow-scrolling:touch]">
            <table className="w-full min-w-[48rem] text-left text-base">
              <thead className="border-neutral-200 border-b bg-[#f7f7f7]">
                <tr className="fa-text-caption font-semibold text-neutral-500 uppercase tracking-wide">
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">摘要</th>
                  <th className="px-4 py-3">会话 ID</th>
                  <th className="px-4 py-3">计划版本</th>
                  <th className="px-4 py-3">创建时间</th>
                  <th className="px-4 py-3">更新时间</th>
                  <th className="min-w-[7rem] px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200">
                {data.items.map((task) => {
                  const colors =
                    STATUS_COLOR_MAP[task.status as TaskStatus] ??
                    STATUS_COLOR_MAP.pending
                  const blockDelete =
                    task.status === 'pending' || task.status === 'running'
                  const canCancel = blockDelete
                  return (
                    <tr key={task.id} className="transition-colors hover:bg-neutral-50/95">
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
                        <Link to={`/tasks/${task.id}`} className="hover:text-primary-700">
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
                      <td className="px-4 py-3 text-right">
                        <div className="flex flex-wrap justify-end gap-1">
                          {canCancel && (
                            <button
                              type="button"
                              className="fa-btn-secondary py-1 px-2 text-xs text-amber-800 border-amber-200 hover:bg-amber-50"
                              disabled={cancelMutation.isPending}
                              onClick={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                setTaskToCancel(task)
                              }}
                            >
                              取消
                            </button>
                          )}
                          <button
                            type="button"
                            className="fa-btn-text-danger"
                            disabled={blockDelete}
                            title={
                              blockDelete ? '进行中的任务请稍后再删' : '删除任务'
                            }
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              setTaskToDelete(task)
                            }}
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            </div>
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
            <span className="text-base text-neutral-500 tabular-nums">
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
