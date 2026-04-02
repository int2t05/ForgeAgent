/**
 * 工具注册表 API 请求函数（与 API.md §7 对齐）。
 */

import { get, post } from '@/api/client'
import type { ToolsListResponse } from '@/types/tool'

/** 获取已注册工具列表（只读快照）。 */
export function getTools(): Promise<ToolsListResponse> {
  return get<ToolsListResponse>('/api/v1/tools')
}

/** 重建工具注册表并返回最新列表（环境变量或 MCP / Skills 变更后调用）。 */
export function refreshToolsRegistry(): Promise<ToolsListResponse> {
  return post<ToolsListResponse>('/api/v1/tools/refresh')
}
