/**
 * 任务执行时间线容器：连接状态、错误提示与事件列表（阶段7）。
 */

import { ErrorAlert } from '@/modules/shell/components/common/ErrorAlert'
import { TaskEventRow } from '@/modules/tasks/components/task/TaskEventRow'
import { EmptyState } from '@/modules/shell/components/common/EmptyState'
import type { TimelineConnectionState } from '@/modules/tasks/hooks/useTaskTimeline'
import type { TaskEvent } from '@/modules/tasks/types/task'

export interface TaskTimelineProps {
  events: TaskEvent[]
  connectionState: TimelineConnectionState
  loadError: string | null
}

function connectionHint(state: TimelineConnectionState): string {
  switch (state) {
    case 'idle':
      return ''
    case 'bootstrapping':
      return '正在加载历史事件…'
    case 'streaming':
      return '实时事件流已连接'
    case 'closed':
      return '事件流已结束'
    case 'error':
      return '事件流异常，已展示已加载数据'
    default:
      return ''
  }
}

export function TaskTimeline({ events, connectionState, loadError }: TaskTimelineProps) {
  const hint = connectionHint(connectionState)

  return (
    <div className="flex flex-col gap-4">
      {loadError && events.length === 0 && (
        <ErrorAlert message="无法加载时间线" detail={loadError} dismissible={false} />
      )}

      {loadError && events.length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-base text-amber-900">
          部分实时数据可能未完整：{loadError}
        </p>
      )}

      {hint && (
        <p className="fa-text-caption text-neutral-500">
          <span
            className={`mr-2 inline-block h-2 w-2 rounded-full align-middle ${
              connectionState === 'streaming' ? 'animate-pulse bg-primary-500' : 'bg-neutral-300'
            }`}
          />
          {hint}
        </p>
      )}

      {events.length === 0 && connectionState !== 'bootstrapping' && !loadError && (
        <EmptyState title="暂无事件" description="任务尚未产生可观测事件" />
      )}

      {events.length === 0 && connectionState === 'bootstrapping' && (
        <p className="text-base text-neutral-500">加载中…</p>
      )}

      {events.length > 0 && (
        <ol className="flex flex-col gap-3">
          {events.map((ev) => (
            <li key={ev.seq}>
              <TaskEventRow event={ev} />
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
