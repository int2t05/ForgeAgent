/**
 * 任务详情页：计划区 + 执行时间线 + 错误高亮。
 * 阶段7：REST 分页历史 + SSE 增量合并的时间线与详情轮询刷新。
 */

import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Header } from '@/layouts/Header'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useTaskDetail } from '@/hooks/useTaskDetail'
import { useTaskTimeline } from '@/hooks/useTaskTimeline'
import { TaskPlanSteps } from '@/components/task/TaskPlanSteps'
import { TaskTimeline } from '@/components/task/TaskTimeline'
import { deleteTask, patchTask } from '@/api/tasks'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP } from '@/constants/task'
import { formatDateTime } from '@/utils/format'
import {
  latestPlanStepsFromEvents,
  normalizePlanStepsFromUnknown,
} from '@/utils/normalizeTaskPlan'
import type { TaskStatus } from '@/types/task'

export function TaskDetailPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { taskId } = useParams<{ taskId: string }>()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const { data: task, isLoading, error } = useTaskDetail(taskId)
  const { events, connectionState, loadError } = useTaskTimeline(taskId)

  const deleteMutation = useMutation({
    mutationFn: () => deleteTask(taskId!),
    onSuccess: () => {
      setConfirmDelete(false)
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      void queryClient.removeQueries({ queryKey: ['task', taskId] })
      void navigate('/tasks', { replace: true })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: () => patchTask(taskId!, { status: 'cancelled' }),
    onSuccess: () => {
      setConfirmCancel(false)
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      void queryClient.invalidateQueries({ queryKey: ['task', taskId] })
    },
  })

  const planSteps = useMemo(() => {
    if (!task) return null
    const fromApi = normalizePlanStepsFromUnknown(task.plan)
    if (fromApi?.length) return fromApi
    return latestPlanStepsFromEvents(events)
  }, [task, events])

  if (isLoading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Header title="任务详情" />
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <LoadingSpinner />
        </div>
      </div>
    )
  }

  if (error || !task) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Header title="任务详情" />
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-6">
          <ErrorAlert
            message="加载任务失败"
            detail={error instanceof Error ? error.message : '任务不存在'}
          />
          <Link to="/tasks" className="fa-link mt-4 inline-block text-base">
            ← 返回任务列表
          </Link>
        </div>
      </div>
    )
  }

  const statusColors =
    STATUS_COLOR_MAP[task.status as TaskStatus] ?? STATUS_COLOR_MAP.pending
  const statusLabel = STATUS_LABEL_MAP[task.status as TaskStatus] ?? task.status
  const blockDelete =
    task.status === 'pending' || task.status === 'running'
  const canCancel = blockDelete

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ConfirmDialog
        open={confirmCancel}
        title="取消任务"
        description="取消后状态将变为「已取消」，后台执行将不再覆盖该状态。"
        confirmLabel="取消任务"
        pending={cancelMutation.isPending}
        onCancel={() => !cancelMutation.isPending && setConfirmCancel(false)}
        onConfirm={() => cancelMutation.mutate()}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="删除任务"
        description="确定删除此任务及全部事件记录？此操作不可恢复。"
        confirmLabel="删除"
        pending={deleteMutation.isPending}
        onCancel={() => !deleteMutation.isPending && setConfirmDelete(false)}
        onConfirm={() => deleteMutation.mutate()}
      />

      <div className="shrink-0">
        <Header
          title="任务详情"
          actions={
            <div className="flex flex-wrap items-center justify-end gap-2">
              {canCancel && (
                <button
                  type="button"
                  className="fa-btn-secondary"
                  disabled={cancelMutation.isPending}
                  onClick={() => setConfirmCancel(true)}
                >
                  取消任务
                </button>
              )}
              <button
                type="button"
                className="fa-btn-secondary border-red-200 text-red-700 hover:bg-red-50 hover:border-red-300"
                disabled={blockDelete}
                title={blockDelete ? '进行中的任务无法删除' : undefined}
                onClick={() => setConfirmDelete(true)}
              >
                删除任务
              </button>
              <Link
                to="/tasks"
                className="fa-btn-secondary inline-flex items-center justify-center no-underline"
              >
                ← 返回列表
              </Link>
            </div>
          }
        />
      </div>

      <div className="fa-reveal min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-6">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-8">
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

        {/* 顶部概览 */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-base font-medium ${statusColors.bg} ${statusColors.text}`}
          >
            <span className={`h-2 w-2 rounded-full ${statusColors.dot}`} />
            {statusLabel}
          </span>
          <span className="text-base text-neutral-500 tabular-nums">
            计划版本 v{task.plan_version}
          </span>
          <span className="fa-text-caption text-neutral-500">
            创建于 {formatDateTime(task.created_at)}
          </span>
        </div>

        <dl className="flex flex-wrap gap-x-6 gap-y-1 border-neutral-200/80 border-y py-3">
          <div className="flex min-w-0 max-w-full items-baseline gap-2">
            <dt className="fa-kv-label shrink-0">task_id</dt>
            <dd className="fa-kv-value-mono min-w-0 truncate" title={task.id}>
              {task.id}
            </dd>
          </div>
          <div className="flex min-w-0 max-w-full items-baseline gap-2">
            <dt className="fa-kv-label shrink-0">session_id</dt>
            <dd className="fa-kv-value-mono min-w-0 truncate" title={task.session_id}>
              {task.session_id}
            </dd>
          </div>
        </dl>

        {/* 摘要 */}
        {task.summary && <p className="text-base text-neutral-700 leading-relaxed">{task.summary}</p>}

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

        {/* 错误信息 */}
        {task.error_message && (
          <ErrorAlert
            message="执行错误"
            detail={task.error_message}
            dismissible={false}
          />
        )}

        {/* LLM 规划步骤（API plan + 时间线 plan_created 合并，避免仅 JSON 占位） */}
        <section>
          <h2 className="fa-section-title">执行计划</h2>
          {planSteps?.length ? (
            <TaskPlanSteps steps={planSteps} />
          ) : task.status === 'running' || task.status === 'pending' ? (
            <p className="fa-text-caption text-neutral-500">规划生成中…</p>
          ) : (
            <p className="fa-text-caption text-neutral-500">暂无计划数据</p>
          )}
        </section>

        {/* 执行时间线：REST 历史 + SSE 增量（GET /events + SSE） */}
        <section>
          <h2 className="fa-section-title">执行时间线</h2>
          <TaskTimeline
            events={events}
            connectionState={connectionState}
            loadError={loadError}
          />
        </section>
        </div>
      </div>
    </div>
  )
}
