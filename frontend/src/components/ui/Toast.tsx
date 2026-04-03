/**
 * 右下角 Toast 通知组件。
 */
import { useEffect, useState } from 'react'
import { useToastStore, type ToastType } from '@/store/toastStore'

const TOAST_STYLE_MAP: Record<
  ToastType,
  { bg: string; border: string; icon: string; iconColor: string }
> = {
  success: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    icon: '✓',
    iconColor: 'text-emerald-600',
  },
  error: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    icon: '✕',
    iconColor: 'text-red-600',
  },
  info: {
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    icon: 'ℹ',
    iconColor: 'text-blue-600',
  },
  warning: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: '⚠',
    iconColor: 'text-amber-600',
  },
}

function ToastItem({
  id,
  type,
  title,
  description,
  onRemove,
}: {
  id: string
  type: ToastType
  title: string
  description?: string
  onRemove: (id: string) => void
}) {
  const [isVisible, setIsVisible] = useState(false)
  const [isLeaving, setIsLeaving] = useState(false)
  const style = TOAST_STYLE_MAP[type]

  useEffect(() => {
    const enterTimer = setTimeout(() => setIsVisible(true), 10)
    return () => clearTimeout(enterTimer)
  }, [])

  function handleClose() {
    setIsLeaving(true)
    setTimeout(() => onRemove(id), 300)
  }

  return (
    <div
      className={`
        pointer-events-auto w-full max-w-sm overflow-hidden rounded-lg border shadow-lg transition-all duration-300
        ${style.bg} ${style.border}
        ${isVisible && !isLeaving ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}
      `}
      role="alert"
    >
      <div className="flex items-start p-4">
        <div className={`mr-3 flex-shrink-0 text-lg font-semibold ${style.iconColor}`}>
          {style.icon}
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-neutral-900">{title}</p>
          {description && (
            <p className="mt-1 text-sm text-neutral-600">{description}</p>
          )}
        </div>
        <button
          type="button"
          className="ml-4 flex-shrink-0 text-neutral-400 hover:text-neutral-600 focus:outline-none"
          onClick={handleClose}
          aria-label="关闭通知"
        >
          <span className="text-lg">×</span>
        </button>
      </div>
    </div>
  )
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const removeToast = useToastStore((s) => s.removeToast)

  if (toasts.length === 0) return null

  return (
    <div
      className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col gap-3"
      aria-live="polite"
      aria-label="通知区域"
    >
      {toasts.map((toast) => (
        <ToastItem
          key={toast.id}
          id={toast.id}
          type={toast.type}
          title={toast.title}
          description={toast.description}
          onRemove={removeToast}
        />
      ))}
    </div>
  )
}
