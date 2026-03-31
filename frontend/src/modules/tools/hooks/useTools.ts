/**
 * 工具列表 TanStack Query Hook。
 */

import { useQuery } from '@tanstack/react-query'
import { getTools } from '@/modules/tools/api/tools'

export function useTools() {
  return useQuery({
    queryKey: ['tools'],
    queryFn: getTools,
    staleTime: 60_000,
  })
}
