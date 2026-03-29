/**
 * 任务列表 TanStack Query Hook（分页、状态筛选）。
 */

import { useQuery } from '@tanstack/react-query'
import { getTasks, type GetTasksParams } from '@/api/tasks'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

export function useTasks(params?: GetTasksParams) {
  const limit = params?.limit ?? DEFAULT_PAGE_SIZE
  const offset = params?.offset ?? 0

  return useQuery({
    queryKey: ['tasks', { limit, offset, status: params?.status }],
    queryFn: () => getTasks({ limit, offset, status: params?.status }),
  })
}
