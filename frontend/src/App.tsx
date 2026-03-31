/**
 * 根组件：包裹 TanStack QueryClientProvider 与 React Router RouterProvider。
 */

import { Suspense } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router/dom'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { createQueryClient } from '@/plugins/react-query'
import { router } from '@/router'

const queryClient = createQueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Suspense
        fallback={
          <div className="flex h-screen items-center justify-center bg-neutral-50">
            <LoadingSpinner text="加载页面…" />
          </div>
        }
      >
        <RouterProvider router={router} />
      </Suspense>
    </QueryClientProvider>
  )
}

export default App
