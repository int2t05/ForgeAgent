/**
 * 设置资源 API 请求函数（与 API.md §6 对齐）。
 */

import { del, get, patch, put } from '@/api/client'
import type {
  Settings,
  SettingsPatch,
  SettingsUpdateResponse,
} from '@/types/settings'

/** 获取当前设置（脱敏）。 */
export function getSettings(): Promise<Settings> {
  return get<Settings>('/api/v1/settings')
}

/** 更新非敏感设置项。 */
export function updateSettings(body: Settings): Promise<SettingsUpdateResponse> {
  return put<SettingsUpdateResponse>('/api/v1/settings', body)
}

/** 部分更新设置。 */
export function patchSettings(
  body: SettingsPatch,
): Promise<SettingsUpdateResponse> {
  return patch<SettingsUpdateResponse>('/api/v1/settings', body)
}

/** 重置为空列表（可读写项）。 */
export function resetSettings(): Promise<SettingsUpdateResponse> {
  return del<SettingsUpdateResponse>('/api/v1/settings')
}
