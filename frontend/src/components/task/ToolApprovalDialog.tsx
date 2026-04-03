/**
 * 工具审批弹窗：敏感工具执行前弹出，用户选择批准或拒绝。
 */

import { useState } from 'react'
import { approveTool, rejectTool } from '@/api/approvals'
import type { ToolApprovalRequiredEvent } from '@/types/approval'

export function ToolApprovalDialog({
  open,
  taskId,
  event,
  onClose,
}: {
  open: boolean
  taskId: string
  event: ToolApprovalRequiredEvent | null
  onClose: () => void
}) {
  const [action, setAction] = useState<'idle' | 'approving' | 'rejecting'>('idle')
  const [error, setError] = useState<string | null>(null)

  if (!open || !event) return null

  async function handleApprove() {
    setAction('approving')
    setError(null)
    try {
      await approveTool(taskId, event.approval_id)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败')
      setAction('idle')
    }
  }

  async function handleReject() {
    setAction('rejecting')
    setError(null)
    try {
      await rejectTool(taskId, event.approval_id)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败')
      setAction('idle')
    }
  }

  const argsPreview = JSON.stringify(event.args, null, 2)
  const isLongArgs = argsPreview.length > 300

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-lg rounded-xl bg-white shadow-xl">
        <div className="border-b border-neutral-100 px-6 py-4">
          <h3 className="text-base font-semibold text-neutral-800">
            ⚠️ 工具执行确认
          </h3>
        </div>

        <div className="px-6 py-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              敏感工具
            </span>
            <code className="text-sm font-semibold text-neutral-800">
              {event.tool}
            </code>
          </div>

          <p className="mb-3 text-sm text-neutral-600">
            Agent 即将执行上述工具，请确认是否允许：
          </p>

          <div className="max-h-48 overflow-auto rounded-md bg-neutral-50 p-3">
            <pre className="whitespace-pre-wrap break-all text-xs font-mono text-neutral-700">
              {isLongArgs ? argsPreview.slice(0, 300) + '…' : argsPreview}
            </pre>
          </div>

          {error && (
            <p className="mt-3 text-sm text-red-600">{error}</p>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-neutral-100 px-6 py-4">
          <button
            type="button"
            className="fa-btn-secondary py-2"
            disabled={action !== 'idle'}
            onClick={handleReject}
          >
            {action === 'rejecting' ? '拒绝中…' : '拒绝'}
          </button>
          <button
            type="button"
            className="fa-btn-primary py-2"
            disabled={action !== 'idle'}
            onClick={handleApprove}
          >
            {action === 'approving' ? '批准中…' : '批准执行'}
          </button>
        </div>
      </div>
    </div>
  )
}
