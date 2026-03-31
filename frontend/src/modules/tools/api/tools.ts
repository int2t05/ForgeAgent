/**
 * 工具注册表 API 请求函数（与 API.md §7 对齐）。
 */

import { get } from '@/core/api/client'
import type { ToolsListResponse } from '@/modules/tools/types/tool'

/** 获取已注册工具列表（只读）。 */
export function getTools(): Promise<ToolsListResponse> {
  return get<ToolsListResponse>('/api/v1/tools')
}
