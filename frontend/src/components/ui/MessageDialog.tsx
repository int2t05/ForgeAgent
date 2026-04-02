/**
 * 信息/结果弹窗：单主按钮，用于保存成功等非危险反馈（与 ConfirmDialog 视觉一致）。
 */

interface MessageDialogProps {
  open: boolean
  title: string
  description?: string
  /** 主按钮文案，默认「知道了」。 */
  confirmLabel?: string
  onClose: () => void
}

export function MessageDialog({
  open,
  title,
  description,
  confirmLabel = '知道了',
  onClose,
}: MessageDialogProps) {
  if (!open) return null

  return (
    <div
      className="fa-dialog-backdrop fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="fa-dialog-panel fa-card w-full max-w-md p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="fa-message-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="fa-message-dialog-title"
          className="font-display text-base font-semibold tracking-tight text-neutral-900"
        >
          {title}
        </h2>
        {description ? (
          <p className="mt-2 text-base leading-relaxed text-neutral-600">{description}</p>
        ) : null}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button type="button" className="fa-btn-primary" onClick={onClose}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
