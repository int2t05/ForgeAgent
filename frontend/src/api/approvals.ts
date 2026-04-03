/**
 * 工具审批资源 API 请求函数。
 */

import { del, get, post } from '@/api/client'
import type { ApprovalListResponse, ApproveResponse } from '@/types/approval'

/** 获取指定任务下待审批列表。 */
export function getPendingApprovals(taskId: string): Promise<ApprovalListResponse> {
  return get<ApprovalListResponse>(`/api/v1/tasks/${taskId}/approvals`)
}

/** 批准工具执行。 */
export function approveTool(
  taskId: string,
  approvalId: string,
): Promise<ApproveResponse> {
  return post<ApproveResponse>(
    `/api/v1/tasks/${taskId}/approvals/${approvalId}/approve`,
    {},
  )
}

/** 拒绝工具执行。 */
export function rejectTool(
  taskId: string,
  approvalId: string,
): Promise<ApproveResponse> {
  return post<ApproveResponse>(
    `/api/v1/tasks/${taskId}/approvals/${approvalId}/reject`,
    {},
  )
}
