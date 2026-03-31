/**
 * 工具注册表类型定义（只读；与后端 Schema 对齐）。
 */

export type ToolSource = 'builtin' | 'mcp' | 'skill'

/** 统一工具描述。 */
export interface ToolInfo {
  name: string
  description: string
  source: ToolSource
  read_only?: boolean
}

/** GET /tools 响应。 */
export interface ToolsListResponse {
  tools: ToolInfo[]
}
