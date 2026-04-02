/**
 * 应用设置类型定义（仅非密钥字段；与后端 Schema 对齐）。
 */

/** GET/PUT /settings 公开字段。 */
export interface Settings {
  mcp: unknown[]
  skills_paths: string[]
  /** 工作区路径；null/省略表示用环境变量 AGENT_WORKSPACE_ROOT */
  agent_workspace_root: string | null
}

/** PUT /settings 响应。 */
export interface SettingsUpdateResponse {
  ok: boolean
}

/** PATCH /settings：部分字段。 */
export interface SettingsPatch {
  mcp?: unknown[]
  skills_paths?: string[]
  agent_workspace_root?: string | null
}
