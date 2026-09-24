import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { InstallPlan, InstallStatus, SettingsField, SettingsConflict } from '../../types/domain'
import { settingValue } from '../settings/settings-transactions'
import { useInstallStatus, type Observation } from './useInstallStatus'
import { isCommunicationError } from './installation-connection'
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
  const [observation, setObservation] = useState<Observation | null>(null)
  const [cancelPending, setCancelPending] = useState(false)
  const receiveStatus = useCallback((status: InstallStatus) => {
    setInstallState(status)
    setCancelPending(false)
  }, [])
  const connection = useInstallStatus(client, observation, receiveStatus)
  const observe = (status: InstallStatus) => {
    setInstallState(status)
    setObservation(['running', 'canceling', 'resolving', 'awaiting_resolution'].includes(status.status) ? { target: { installId: status.install_id } } : null)
  }
  const query = useQuery({
    queryKey: ['capabilities'],
    queryFn: () => client.getCapabilities(),
    refetchOnMount: 'always',
    enabled: !observation || connection.phase === 'connected',
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
      // Earlier actions may have verified and saved paths even if a later action failed.
      await Promise.all([
        query.refetch(),
        queryClient.invalidateQueries({ queryKey: ['settings'] }),
      ])
      if (installState.status === 'completed') {
        onNotice('Installation complete and verified')
      } else if (installState.status === 'failed') {
        onError(installState.error ?? 'Dependency installation failed')
      }
      setInstallState((current) => current?.install_id === installState.install_id ? null : current)
      setObservation((current) => current === observation ? null : current)
    })()
  }, [installState, observation, onError, onNotice, query, queryClient])

  const installMutation = useMutation({
    mutationFn: (planId: string) => client.installDependencies(planId),
    onMutate: (planId) => {
      setPendingPlan(null)
      setInstallState({ install_id: `pending:${planId}`, status: 'running', message: 'Starting approved setup',
        action_id: null, action_index: null, action_count: null, started_at: null, phase: 'starting', completed_bytes: null, total_bytes: null, error: null })
    },
    onSuccess: observe,
    onError: (reason, planId) => {
      if (isCommunicationError(reason)) {
        // A missing acknowledgement is not permission to replay approval.
        setObservation({ target: { planId }, failure: reason })
      } else {
        setInstallState(null)
        onError(errorMessage(reason))
      }
    },
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
      observe(updated)
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  const resolveMutation = useMutation({
    mutationFn: (choices: Partial<Record<SettingsField, boolean>>) => {
      if (!installState?.resolution) throw new Error('No component settings are awaiting review')
      const selected = Object.fromEntries(Object.entries(choices).map(([field, value]) => [field, value ? 'use_verified' : 'keep_current'])) as Partial<Record<SettingsField, 'keep_current' | 'use_verified'>>
      setObservation(null)
      return client.resolveInstallConflict(installState.install_id, installState.resolution.snapshot.revision, selected)
    },
    onSuccess: observe,
    onError: (reason) => {
      if (installState && isCommunicationError(reason)) setObservation({ target: { installId: installState.install_id }, failure: reason })
      else onError(errorMessage(reason))
    },
  })
  const conflicts: SettingsConflict[] = installState?.resolution
    ? Object.entries(installState.verified_values ?? {}).map(([field, proposed]) => ({
      field: field as SettingsField,
      expected: installState.resolution!.conflicts.find((item) => item.field === field)?.expected ?? null,
      current: settingValue(installState.resolution!.snapshot.settings, field as SettingsField),
      proposed: proposed ?? null,
    })) : []

  return {
    connection,
    cancelPending,
    retryConnection: () => {
      if (observation) setObservation({ target: observation.target, failure: { code: 'request_timeout' } })
    },
    restart: () => { void client.restart().catch((reason) => onError(errorMessage(reason))) },
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
      if (!installState || cancelPending || installState.install_id.startsWith('pending:')) return
      setCancelPending(true)
      // Reconcile either acknowledgement through a fresh read; an older cancel
      // response cannot replace newer progress or claim that cancellation finished.
      setObservation(null)
      try {
        await client.cancelInstall(installState.install_id)
        setObservation({ target: { installId: installState.install_id } })
      } catch (reason) {
        setObservation({ target: { installId: installState.install_id }, failure: reason })
      }
    },
    approveInstall: async () => {
      if (!pendingPlan || installMutation.isPending || installState) return
      await installMutation.mutateAsync(pendingPlan.plan_id).catch(() => undefined)
    },
    locateExisting: async (component: 'ffmpeg' | 'whisper_model' | 'ytdlp') => {
      await locateMutation.mutateAsync(component).catch(() => undefined)
    },
  }
}
