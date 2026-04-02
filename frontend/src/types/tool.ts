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
  /** OpenAPI/JSON Schema 风格入参（与后端 LangChain args_schema 对齐）。 */
  parameters?: Record<string, unknown> | null
}

/** GET /tools 响应。 */
export interface ToolsListResponse {
  tools: ToolInfo[]
}
