/**
 * 工具审批相关类型定义（与后端 Schema 对齐）。
 */

/** 审批状态。 */
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'timeout' | 'cancelled'

/** 单条审批请求。 */
export interface ApprovalItem {
  id: string
  task_id: string
  tool_name: string
  tool_args: Record<string, unknown>
  status: ApprovalStatus
}

/** GET 待审批列表响应。 */
export interface ApprovalListResponse {
  items: ApprovalItem[]
}

/** 批准/拒绝操作响应。 */
export interface ApproveResponse {
  ok: boolean
  message: string
}

/** SSE 事件中的审批请求 payload。 */
export interface ToolApprovalRequiredEvent {
  step_id?: string
  tool: string
  args: Record<string, unknown>
  mode: string
  approval_id: string
}

/** SSE 事件中的审批结果 payload。 */
export interface ToolApprovalResultEvent {
  step_id?: string
  tool: string
  approval_id: string
  status: ApprovalStatus
}
