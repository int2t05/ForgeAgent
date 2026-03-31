/**
 * 404 页面：未匹配路由时展示。
 */

import { Link } from 'react-router'
import { Header } from '@/modules/shell/components/layout/Header'

export function NotFoundPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain">
      <Header title="页面未找到" />

      <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-6 py-8">
        <div className="fa-blueprint-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="fa-reveal relative text-center">
          <p className="font-display text-[clamp(4rem,14vw,7rem)] font-bold leading-none tracking-tighter text-neutral-600">
            404
          </p>
          <p className="mt-4 text-base text-neutral-500 leading-relaxed">
            请求的页面不存在，或链接已失效
          </p>
          <Link
            to="/"
            className="fa-btn-primary mt-8 inline-flex min-w-[9rem] justify-center text-center"
          >
            返回对话
          </Link>
        </div>
      </div>
    </div>
  )
}
