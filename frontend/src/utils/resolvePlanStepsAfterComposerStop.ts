import type { QueryClient } from '@tanstack/react-query'
import { getTask, getTaskEvents } from '@/api/tasks'
import { useComposerTaskStore } from '@/store/composerTaskStore'
import {
  latestPlanStepsFromEvents,
  normalizePlanStepsFromUnknown,
} from '@/utils/normalizeTaskPlan'
import type { PlanStep } from '@/utils/normalizeTaskPlan'

/**
 * 停止任务后尽量恢复「本轮规划步骤」：内存 live/sticky → clearPending 归档 → 任务详情 → 事件拉取。
 * 顺序与 clearPending 交互敏感，勿在 clear 前遗漏 live 快照。
 */
export async function resolvePlanStepsAfterComposerStop(
  taskId: string,
  queryClient: QueryClient,
): Promise<PlanStep[] | null> {
  const store = useComposerTaskStore.getState()
  const fromLive = latestPlanStepsFromEvents(store.liveTaskEvents)
  const pendSid = store.pendingSessionId
  const fromSticky =
    pendSid != null ? store.stickyPlansBySession[pendSid] : undefined
  const snapshot =
    fromLive?.length ? fromLive : fromSticky?.length ? fromSticky : null

  store.clearPending()

  const archived = useComposerTaskStore.getState().plansByTaskId[taskId]?.steps
  if (archived?.length) return archived
  if (snapshot?.length) return snapshot

  try {
    const detail = await queryClient.fetchQuery({
      queryKey: ['task', taskId],
      queryFn: () => getTask(taskId),
    })
    const fromApi = normalizePlanStepsFromUnknown(detail.plan ?? null)
    if (fromApi?.length) return fromApi
  } catch {
    /* 网络/404 时继续尝试事件 */
  }

  try {
    const { events } = await getTaskEvents(taskId, undefined, 200)
    return latestPlanStepsFromEvents(events)
  } catch {
    return null
  }
}
