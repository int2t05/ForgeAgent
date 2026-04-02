/**
 * 工作区 API 类型（与 OpenAPI / GET /api/v1/workspace 一致）。
 */

export interface WorkspaceEntry {
  name: string
  path: string
  is_dir: boolean
  /** 文件字节数；目录为 null */
  size_bytes?: number | null
}

export interface WorkspaceSnapshotResponse {
  workspace_root: string
  current_path: string
  /** 已在根目录时为 null */
  parent_path: string | null
  workspace_listing: WorkspaceEntry[]
  workspace_listing_truncated: boolean
}
