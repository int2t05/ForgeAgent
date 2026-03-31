/**
 * 第三方库初始化：TanStack Query 默认客户端。
 */

import { QueryClient } from '@tanstack/react-query'

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 60_000,
        gcTime: 5 * 60_000,
      },
    },
  })
}
