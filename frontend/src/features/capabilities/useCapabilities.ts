import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { InstallPlan, InstallStatus, SettingsField, SettingsConflict } from '../../types/domain'
import { settingValue } from '../settings/settings-transactions'
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
    refetchOnMount: 'always',
    refetchInterval: (currentQuery) => currentQuery.state.data?.app_runtime === 'ready' ? false : 3000,
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
    const active = ['running', 'canceling', 'resolving'].includes(installState.status)
    if (active || installState.status === 'awaiting_resolution') return

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

  const activeInstallId = installState && ['running', 'canceling', 'resolving'].includes(installState.status)
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
    mutationFn: async (component: 'ffmpeg' | 'whisper_model' | 'ytdlp') => {
      if (component === 'ffmpeg') {
        const selected = await client.selectFile(query.data?.ffmpeg_path ?? undefined)
        return selected ? client.locateExistingFfmpeg(selected) : null
      }
      if (component === 'ytdlp') {
        const selected = await client.selectFile(query.data?.ytdlp_path ?? undefined)
        return selected ? client.locateExistingYtdlp(selected) : null
      }
      const selected = await client.selectDirectory()
      return selected ? client.locateExistingModel(selected) : null
    },
    onSuccess: async (updated) => {
      if (!updated) return
      setInstallState(updated)
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  const resolveMutation = useMutation({
    mutationFn: (choices: Partial<Record<SettingsField, boolean>>) => {
      if (!installState?.resolution) throw new Error('No component settings are awaiting review')
      const selected = Object.fromEntries(Object.entries(choices).map(([field, value]) => [field, value ? 'use_verified' : 'keep_current'])) as Partial<Record<SettingsField, 'keep_current' | 'use_verified'>>
      return client.resolveInstallConflict(installState.install_id, installState.resolution.snapshot.revision, selected)
    },
    onSuccess: setInstallState,
    onError: (reason) => onError(errorMessage(reason)),
  })
  const conflicts: SettingsConflict[] = installState?.resolution
    ? Object.entries(installState.verified_values ?? {}).map(([field, proposed]) => ({
      field: field as SettingsField,
      expected: installState.resolution!.conflicts.find((item) => item.field === field)?.expected ?? null,
      current: settingValue(installState.resolution!.snapshot.settings, field as SettingsField),
      proposed: proposed ?? null,
    })) : []

  return {
    conflicts,
    resolving: resolveMutation.isPending,
    resolveConflict: (choices: Partial<Record<SettingsField, boolean>>) => resolveMutation.mutate(choices),
    capabilities: query.data ?? null,
    loading: query.isLoading,
    checking: query.isFetching,
    busy: Boolean(installState && ['awaiting_resolution', 'running', 'canceling', 'resolving'].includes(installState.status)) || planMutation.isPending || installMutation.isPending || locateMutation.isPending || query.isFetching,
    installing: installMutation.isPending || Boolean(installState && ['running', 'canceling', 'resolving'].includes(installState.status)),
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
    locateExisting: async (component: 'ffmpeg' | 'whisper_model' | 'ytdlp') => {
      await locateMutation.mutateAsync(component).catch(() => undefined)
    },
  }
}
