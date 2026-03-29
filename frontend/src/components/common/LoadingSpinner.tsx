/**
 * 加载动画组件：居中旋转圆环指示器。
 */

interface LoadingSpinnerProps {
  /** 额外 CSS 类名。 */
  className?: string
  /** 提示文案（默认「加载中…」）。 */
  text?: string
}

export function LoadingSpinner({
  className = '',
  text = '加载中…',
}: LoadingSpinnerProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 py-12 ${className}`}
    >
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-200 border-t-blue-600" />
      {text && <span className="text-sm text-neutral-500">{text}</span>}
    </div>
  )
}
