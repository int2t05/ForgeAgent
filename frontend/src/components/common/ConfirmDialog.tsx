/**
 * 通用确认对话框：与 fa-btn-secondary / fa-btn-danger 配合，用于删除等危险操作。
 */

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  cancelLabel?: string
  /** danger：确认按钮使用 fa-btn-danger。 */
  variant?: 'danger' | 'primary'
  pending?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = '取消',
  variant = 'danger',
  pending = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  const confirmClass =
    variant === 'danger' ? 'fa-btn-danger' : 'fa-btn-primary'

  return (
    <div
      className="fa-dialog-backdrop fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="presentation"
      onClick={() => !pending && onCancel()}
    >
      <div
        className="fa-dialog-panel fa-card w-full max-w-md p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="font-display text-base font-semibold tracking-tight text-neutral-900"
        >
          {title}
        </h2>
        <p className="mt-2 text-sm text-neutral-600 leading-relaxed">{description}</p>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="fa-btn-secondary"
            disabled={pending}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={confirmClass}
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
