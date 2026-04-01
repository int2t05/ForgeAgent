import { ApiRequestError } from '@/api/client'

/** 将 unknown 错误转为 ErrorAlert 等组件可用的简短文案 */
export function errDetail(e: unknown): string {
  if (e instanceof ApiRequestError) {
    const detail = (e.body?.detail ?? e.message).trim()
    if (!detail) return `请求失败（HTTP ${e.status}）`
    return e.status ? `${detail}（HTTP ${e.status}）` : detail
  }
  if (e instanceof Error) {
    const m = e.message.trim()
    if (m === 'Failed to fetch' || m.includes('NetworkError')) {
      return '无法连接服务器，请检查网络或稍后重试。'
    }
    return m || '未知错误'
  }
  return '未知错误'
}
