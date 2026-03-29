/**
 * 格式化工具函数：日期、文本截断、JSON 安全解析。
 */

/**
 * 将 ISO 8601 时间字符串格式化为本地化短日期时间。
 * @example formatDateTime('2025-03-29T10:00:00Z') → '2025/3/29 18:00:00'
 */
export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

/**
 * 格式化为相对时间描述（如「3 分钟前」）。
 */
export function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime()
    const seconds = Math.floor(diff / 1000)

    if (seconds < 60) return '刚刚'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes} 分钟前`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours} 小时前`
    const days = Math.floor(hours / 24)
    return `${days} 天前`
  } catch {
    return iso
  }
}

/**
 * 截断文本到指定长度，超出部分以省略号替代。
 */
export function truncateText(text: string, maxLen = 100): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '…'
}

/**
 * 安全解析 JSON 字符串，失败时返回 null。
 */
export function safeJsonParse<T = unknown>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}
