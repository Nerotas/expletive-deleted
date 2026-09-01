import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { InstallPlan } from '../../types/domain'
import { errorMessage } from '../../utils/format'

type CapabilitiesOptions = {
  client?: DesktopClient
  onError: (message: string) => void
  onNotice: (message: string) => void
}

export function useCapabilities({
  client = desktopClient,
  onError,
  onNotice,
}: CapabilitiesOptions) {
  const queryClient = useQueryClient()
  const [pendingPlan, setPendingPlan] = useState<InstallPlan | null>(null)
  const query = useQuery({
    queryKey: ['capabilities'],
    queryFn: () => client.getCapabilities(),
  })

  useEffect(() => {
    if (query.error) onError(errorMessage(query.error))
  }, [onError, query.error])

  const planMutation = useMutation({
    mutationFn: (components: string[]) => client.planDependencies(components),
    onSuccess: setPendingPlan,
    onError: (reason) => onError(errorMessage(reason)),
  })

  const installMutation = useMutation({
    mutationFn: (planId: string) => client.installDependencies(planId),
    onSuccess: async () => {
      setPendingPlan(null)
      await Promise.all([
        query.refetch(),
        queryClient.invalidateQueries({ queryKey: ['settings'] }),
      ])
      onNotice('Installation complete and verified')
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  const locateMutation = useMutation({
    mutationFn: async (component: 'ffmpeg' | 'whisper_model') => {
      if (component === 'ffmpeg') {
        const selected = await client.selectFile(query.data?.ffmpeg_path ?? undefined)
        return selected ? client.locateExistingFfmpeg(selected) : null
      }
      const selected = await client.selectDirectory()
      return selected ? client.locateExistingModel(selected) : null
    },
    onSuccess: async (updated) => {
      if (!updated) return
      queryClient.setQueryData(['capabilities'], updated)
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
      onNotice('Existing component located and verified')
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  return {
    capabilities: query.data ?? null,
    loading: query.isLoading,
    checking: query.isFetching,
    busy: planMutation.isPending || installMutation.isPending || locateMutation.isPending || query.isFetching,
    installing: installMutation.isPending,
    pendingPlan,
    refresh: async () => { await query.refetch() },
    reviewInstall: async (components: string[]) => {
      await planMutation.mutateAsync(components).catch(() => undefined)
    },
    cancelInstall: () => setPendingPlan(null),
    approveInstall: async () => {
      if (!pendingPlan) return
      await installMutation.mutateAsync(pendingPlan.plan_id).catch(() => undefined)
    },
    locateExisting: async (component: 'ffmpeg' | 'whisper_model') => {
      await locateMutation.mutateAsync(component).catch(() => undefined)
    },
  }
}
