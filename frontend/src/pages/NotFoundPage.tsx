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
        <Link to="/" className="fa-btn-primary inline-block text-center">
          返回首页
        </Link>
      </div>
    </div>
  )
}
