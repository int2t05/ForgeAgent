/**
 * 单任务详情 TanStack Query Hook。
 */

import { useQuery } from '@tanstack/react-query'
import { getTask } from '@/api/tasks'
import { TERMINAL_STATUSES } from '@/lib/constants'

export function useTaskDetail(taskId: string | undefined) {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => getTask(taskId!),
    enabled: !!taskId,
    refetchInterval: (query) => {
      const row = query.state.data
      if (!row || TERMINAL_STATUSES.has(row.status)) {
        return false
      }
      return 3000
    },
  })
}
