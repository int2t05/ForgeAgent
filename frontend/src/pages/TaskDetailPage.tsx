/**
 * 任务详情页：计划区 + 执行时间线 + 错误高亮。
 * 阶段7：REST 分页历史 + SSE 增量合并的时间线与详情轮询刷新。
 */

import { Link, useParams } from 'react-router'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { useTaskDetail } from '@/hooks/useTaskDetail'
import { useTaskTimeline } from '@/hooks/useTaskTimeline'
import { TaskTimeline } from '@/components/task/TaskTimeline'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import type { TaskStatus } from '@/types/task'

export function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const { data: task, isLoading, error } = useTaskDetail(taskId)
  const { events, connectionState, loadError } = useTaskTimeline(taskId)

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col">
        <Header title="任务详情" />
        <LoadingSpinner />
      </div>
    )
  }

  if (error || !task) {
    return (
      <div className="flex flex-1 flex-col">
        <Header title="任务详情" />
        <div className="px-6 py-6">
          <ErrorAlert
            message="加载任务失败"
            detail={error instanceof Error ? error.message : '任务不存在'}
          />
          <Link to="/tasks" className="fa-link mt-4 inline-block text-sm">
            ← 返回任务列表
          </Link>
        </div>
      </div>
    )
  }

  const statusColors =
    STATUS_COLOR_MAP[task.status as TaskStatus] ?? STATUS_COLOR_MAP.pending
  const statusLabel = STATUS_LABEL_MAP[task.status as TaskStatus] ?? task.status

  return (
    <div className="flex flex-1 flex-col">
      <Header
        title="任务详情"
        actions={
          <Link
            to="/tasks"
            className="text-neutral-500 text-sm transition-colors hover:text-neutral-800"
          >
            ← 返回列表
          </Link>
        }
      />

      <div className="flex flex-1 flex-col gap-6 px-6 py-6">
        {/* 顶部概览 */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${statusColors.bg} ${statusColors.text}`}
          >
            <span className={`h-2 w-2 rounded-full ${statusColors.dot}`} />
            {statusLabel}
          </span>
          <span className="text-neutral-500 text-sm tabular-nums">
            计划版本 v{task.plan_version}
          </span>
          <span className="text-neutral-400 text-sm">
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
        {task.summary && <p className="text-neutral-700 text-sm leading-relaxed">{task.summary}</p>}

        {/* 错误信息 */}
        {task.error_message && (
          <ErrorAlert
            message="执行错误"
            detail={task.error_message}
            dismissible={false}
          />
        )}

        {/* 计划区占位 */}
        <section>
          <h2 className="fa-section-title">执行计划</h2>
          {task.plan ? (
            <pre className="fa-panel max-h-[min(24rem,50vh)]">{JSON.stringify(task.plan, null, 2)}</pre>
          ) : (
            <p className="text-neutral-400 text-sm">暂无计划数据</p>
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
  )
}
