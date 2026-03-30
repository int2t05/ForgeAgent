/**
 * 根组件：包裹 TanStack QueryClientProvider 与 React Router RouterProvider。
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router/dom'
import { router } from '@/router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      /** 减少无意义重拉，列表页更跟手 */
      staleTime: 60_000,
      gcTime: 5 * 60_000,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

export default App
