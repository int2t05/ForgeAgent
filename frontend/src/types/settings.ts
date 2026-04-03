/**
 * 应用设置类型定义（仅非密钥字段；与后端 Schema 对齐）。
 */

/** 工具执行模式。 */
export type ExecutionMode = 'auto' | 'confirm' | 'learn'

/** GET/PUT /settings 公开字段。 */
export interface Settings {
  mcp: unknown[]
  skills_paths: string[]
  /** 工作区路径；null/省略表示用环境变量 AGENT_WORKSPACE_ROOT */
  agent_workspace_root: string | null
  /** 工具执行策略 */
  execution_mode: ExecutionMode
  /** learn 模式下已批准放行的敏感工具名列表 */
  approved_tool_patterns: string[]
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
  execution_mode?: ExecutionMode
  approved_tool_patterns?: string[]
}

/** POST /settings/skills/validate 单条结果。 */
export interface SkillPathCheckItem {
  input_path: string
  resolved_path: string
  is_directory: boolean
  has_skill_md: boolean
  skill_md_filename: string | null
  ok: boolean
  message: string
}

/** POST /settings/skills/validate 响应。 */
export interface SkillPathsValidateResponse {
  items: SkillPathCheckItem[]
  all_ok: boolean
}
