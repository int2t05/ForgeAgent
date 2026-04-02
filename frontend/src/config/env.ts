/**
 * 运行时环境相关配置（由 Vite 注入，不含密钥默认值外的敏感信息）。
 */

/** 后端 API 根 URL（由 Vite 环境变量注入，默认本地开发地址）。 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

/**
 * 与后端 `LLM_CONTEXT_WINDOW_TOKENS` 对齐（仅用于前端用量环估算分母）。
 * 未设置时与仓库默认大窗口模型一致。
 */
export const LLM_CONTEXT_WINDOW_TOKENS: number = (() => {
  const raw = import.meta.env.VITE_LLM_CONTEXT_WINDOW_TOKENS
  if (raw == null || raw === '') return 204_800
  const n = Number(raw)
  return Number.isFinite(n) && n >= 512 ? Math.floor(n) : 204_800
})()
