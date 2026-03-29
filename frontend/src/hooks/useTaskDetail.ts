/**
 * 单任务详情 TanStack Query Hook。
 */

import { useQuery } from '@tanstack/react-query'
import { getTask } from '@/api/tasks'

export function useTaskDetail(taskId: string | undefined) {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => getTask(taskId!),
    enabled: !!taskId,
  })
}
