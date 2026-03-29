/**
 * 应用设置类型定义（仅非密钥字段；与后端 Schema 对齐）。
 */

/** GET/PUT /settings 公开字段。 */
export interface Settings {
  mcp: unknown[]
  skills_paths: string[]
}

/** PUT /settings 响应。 */
export interface SettingsUpdateResponse {
  ok: boolean
}
