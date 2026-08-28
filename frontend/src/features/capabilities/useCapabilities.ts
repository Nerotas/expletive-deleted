import { useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
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
  const query = useQuery({
    queryKey: ['capabilities'],
    queryFn: () => client.getCapabilities(),
  })

  useEffect(() => {
    if (query.error) onError(errorMessage(query.error))
  }, [onError, query.error])

  const installMutation = useMutation({
    mutationFn: async (components: string[]) => {
      const plan = await client.planDependencies(components)
      await client.installDependencies(plan.plan_id)
    },
    onSuccess: async () => {
      await query.refetch()
      onNotice('Installation complete and verified')
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  return {
    capabilities: query.data ?? null,
    loading: query.isLoading,
    busy: installMutation.isPending,
    refresh: async () => { await query.refetch() },
    installRequired: async (components: string[]) => {
      await installMutation.mutateAsync(components).catch(() => undefined)
    },
  }
}
