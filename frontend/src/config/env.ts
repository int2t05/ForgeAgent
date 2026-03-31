/**
 * 运行时环境相关配置（由 Vite 注入，不含密钥默认值外的敏感信息）。
 */

/** 后端 API 根 URL（由 Vite 环境变量注入，默认本地开发地址）。 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
