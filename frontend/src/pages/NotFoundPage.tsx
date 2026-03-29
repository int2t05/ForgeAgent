/**
 * 404 页面：未匹配路由时展示。
 */

import { Link } from 'react-router'
import { Header } from '@/components/layout/Header'

export function NotFoundPage() {
  return (
    <div className="flex flex-1 flex-col">
      <Header title="页面未找到" />

      <div className="flex flex-1 flex-col items-center justify-center gap-4">
        <span className="text-6xl font-bold text-neutral-200">404</span>
        <p className="text-sm text-neutral-500">请求的页面不存在</p>
        <Link
          to="/"
          className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          返回首页
        </Link>
      </div>
    </div>
  )
}
