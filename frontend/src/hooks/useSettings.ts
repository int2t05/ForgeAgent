/**
 * 设置 TanStack Query + Mutation Hook。
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSettings,
  patchSettings,
  resetSettings,
  updateSettings,
} from '@/api/settings'
import type { Settings, SettingsPatch } from '@/types/settings'

export function useSettings() {
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const mutation = useMutation({
    mutationFn: (body: Settings) => updateSettings(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
      void queryClient.invalidateQueries({ queryKey: ['tools'] })
      void queryClient.invalidateQueries({ queryKey: ['workspace', 'snapshot'] })
    },
  })

  const patchMutation = useMutation({
    mutationFn: (body: SettingsPatch) => patchSettings(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
      void queryClient.invalidateQueries({ queryKey: ['tools'] })
      void queryClient.invalidateQueries({ queryKey: ['workspace', 'snapshot'] })
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => resetSettings(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
      void queryClient.invalidateQueries({ queryKey: ['tools'] })
      void queryClient.invalidateQueries({ queryKey: ['workspace', 'snapshot'] })
    },
  })

  return {
    settings: query.data,
    dataUpdatedAt: query.dataUpdatedAt,
    isLoading: query.isLoading,
    error: query.error,
    updateSettings: mutation.mutate,
    isUpdating: mutation.isPending,
    updateError: mutation.error,
    patchSettings: patchMutation.mutate,
    isPatching: patchMutation.isPending,
    patchError: patchMutation.error,
    resetSettings: resetMutation.mutate,
    isResetting: resetMutation.isPending,
    resetError: resetMutation.error,
  }
}
