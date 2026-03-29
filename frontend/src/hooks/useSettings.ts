/**
 * 设置 TanStack Query + Mutation Hook。
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSettings, updateSettings } from '@/api/settings'
import type { Settings } from '@/types/settings'

export function useSettings() {
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const mutation = useMutation({
    mutationFn: (body: Settings) => updateSettings(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  return {
    settings: query.data,
    isLoading: query.isLoading,
    error: query.error,
    updateSettings: mutation.mutate,
    isUpdating: mutation.isPending,
    updateError: mutation.error,
  }
}
