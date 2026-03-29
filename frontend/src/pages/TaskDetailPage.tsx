/**
 * 任务详情页：计划区 + 执行时间线 + 错误高亮。
 * 阶段6 提供布局骨架；阶段7 实现 SSE 实时事件流与完整时间线组件。
 */

import { Link, useParams } from 'react-router'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { useTaskDetail } from '@/hooks/useTaskDetail'
import { STATUS_COLOR_MAP, STATUS_LABEL_MAP } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import type { TaskStatus } from '@/types/task'

export function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const { data: task, isLoading, error } = useTaskDetail(taskId)

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
          <Link
            to="/tasks"
            className="mt-4 inline-block text-sm text-blue-600 hover:text-blue-700"
          >
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
          <Link to="/tasks" className="text-sm text-neutral-500 hover:text-neutral-700">
            ← 返回列表
          </Link>
        }
      />

      <div className="flex flex-1 flex-col gap-6 px-6 py-6">
        {/* 顶部概览 */}
        <div className="flex flex-wrap items-center gap-4">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${statusColors.bg} ${statusColors.text}`}
          >
            <span className={`h-2 w-2 rounded-full ${statusColors.dot}`} />
            {statusLabel}
          </span>
          <span className="text-sm text-neutral-500">
            计划版本 v{task.plan_version}
          </span>
          <span className="text-sm text-neutral-400">
            创建于 {formatDateTime(task.created_at)}
          </span>
        </div>

        {/* 摘要 */}
        {task.summary && <p className="text-sm text-neutral-700">{task.summary}</p>}

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
          <h2 className="mb-3 text-sm font-medium text-neutral-700">执行计划</h2>
          {task.plan ? (
            <pre className="overflow-auto rounded-lg border border-neutral-200 bg-neutral-50 p-4 font-mono text-xs text-neutral-700">
              {JSON.stringify(task.plan, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-neutral-400">暂无计划数据</p>
          )}
        </section>

        {/* 执行时间线占位（阶段7实现） */}
        <section>
          <h2 className="mb-3 text-sm font-medium text-neutral-700">执行时间线</h2>
          <div className="rounded-lg border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-400">
            事件时间线将在阶段7实现（SSE 实时推送 + 增量合并）
          </div>
        </section>
      </div>
    </div>
  )
}
