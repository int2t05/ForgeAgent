/**
 * 设置资源 API 请求函数（与 API.md §6 对齐）。
 */

import { get, put } from '@/api/client'
import type { Settings, SettingsUpdateResponse } from '@/types/settings'

/** 获取当前设置（脱敏）。 */
export function getSettings(): Promise<Settings> {
  return get<Settings>('/api/v1/settings')
}

/** 更新非敏感设置项。 */
export function updateSettings(body: Settings): Promise<SettingsUpdateResponse> {
  return put<SettingsUpdateResponse>('/api/v1/settings', body)
}
