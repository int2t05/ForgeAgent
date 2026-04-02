/**
 * GET /api/v1/workspace：单层目录列举；reload_config 与服务端工具刷新对齐。
 */

import { get } from '@/api/client'
import type { WorkspaceSnapshotResponse } from '@/types/workspace'

export interface GetWorkspaceSnapshotParams {
  /** 要列举的目录绝对路径；省略为当前工作区根 */
  path?: string
  /** true 时服务端从 DB 重读工作区根并重建工具注册表 */
  reloadConfig?: boolean
}

/** 请求工作区目录快照（路径须落在配置的工作区根下）。 */
export function getWorkspaceSnapshot(
  params?: GetWorkspaceSnapshotParams,
): Promise<WorkspaceSnapshotResponse> {
  const built: Record<string, string> = {}
  if (params?.path != null && params.path !== '') {
    built.path = params.path
  }
  if (params?.reloadConfig) {
    built.reload_config = 'true'
  }
  return get<WorkspaceSnapshotResponse>('/api/v1/workspace', built)
}
