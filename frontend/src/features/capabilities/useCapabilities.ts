import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { InstallPlan, InstallStatus } from '../../types/domain'
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
  const [installState, setInstallState] = useState<InstallStatus | null>(null)
  const query = useQuery({
    queryKey: ['capabilities'],
    queryFn: () => client.getCapabilities(),
  })
  const settledInstallRef = useRef<string | null>(null)

  useEffect(() => {
    if (query.error) onError(errorMessage(query.error))
  }, [onError, query.error])

  const planMutation = useMutation({
    mutationFn: (components: string[]) => client.planDependencies(components),
    onSuccess: setPendingPlan,
    onError: (reason) => onError(errorMessage(reason)),
  })

  useEffect(() => {
    if (!installState) return
    const active = ['running', 'canceling'].includes(installState.status)
    if (active) return

    const settledKey = `${installState.install_id}:${installState.status}`
    if (settledInstallRef.current === settledKey) return
    settledInstallRef.current = settledKey

    void (async () => {
      if (installState.status === 'completed') {
        await Promise.all([
          query.refetch(),
          queryClient.invalidateQueries({ queryKey: ['settings'] }),
        ])
        onNotice('Installation complete and verified')
      } else if (installState.status === 'failed') {
        onError(installState.error ?? 'Dependency installation failed')
      }
      setInstallState(null)
    })()
  }, [installState, onError, onNotice, query, queryClient])

  const activeInstallId = installState && ['running', 'canceling'].includes(installState.status)
    ? installState.install_id
    : null

  useEffect(() => {
    if (!activeInstallId) return
    const timer = window.setInterval(() => {
      void client.getInstallStatus(activeInstallId)
        .then((status) => setInstallState(status))
        .catch(() => undefined)
    }, 1200)

    return () => window.clearInterval(timer)
  }, [activeInstallId, client])

  const installMutation = useMutation({
    mutationFn: (planId: string) => client.installDependencies(planId),
    onSuccess: (result) => {
      setPendingPlan(null)
      setInstallState(result)
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
    installing: installMutation.isPending || Boolean(installState && ['running', 'canceling'].includes(installState.status)),
    installState,
    pendingPlan,
    refresh: async () => { await query.refetch() },
    reviewInstall: async (components: string[]) => {
      await planMutation.mutateAsync(components).catch(() => undefined)
    },
    cancelInstall: () => setPendingPlan(null),
    cancelCurrentInstall: async () => {
      if (!installState) return
      const status = await client.cancelInstall(installState.install_id).catch(() => null)
      if (status) setInstallState(status)
    },
    approveInstall: async () => {
      if (!pendingPlan) return
      await installMutation.mutateAsync(pendingPlan.plan_id).catch(() => undefined)
    },
    dismissProgress: () => setInstallState(null),
    locateExisting: async (component: 'ffmpeg' | 'whisper_model') => {
      await locateMutation.mutateAsync(component).catch(() => undefined)
    },
  }
}
