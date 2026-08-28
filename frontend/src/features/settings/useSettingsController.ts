import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { Settings } from '../../types/domain'
import { errorMessage } from '../../utils/format'

type SettingsControllerOptions = {
  client?: DesktopClient
  onError: (message: string) => void
  onNotice: (message: string) => void
  onSaved: () => void | Promise<void>
}

export function useSettingsController({
  client = desktopClient,
  onError,
  onNotice,
  onSaved,
}: SettingsControllerOptions) {
  const queryClient = useQueryClient()
  const form = useForm<Settings>()
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => client.getSettings(),
    staleTime: Number.POSITIVE_INFINITY,
  })
  const watchedDraft = useWatch({ control: form.control }) as Partial<Settings>
  const draft = watchedDraft.directories ? watchedDraft as Settings : null

  useEffect(() => {
    if (settingsQuery.data && !form.formState.isDirty) form.reset(settingsQuery.data)
  }, [form, settingsQuery.data])

  useEffect(() => {
    if (settingsQuery.error) onError(errorMessage(settingsQuery.error))
  }, [onError, settingsQuery.error])

  const saveMutation = useMutation({
    mutationFn: (settings: Settings) => client.updateSettings(settings),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['settings'], updated)
      form.reset(updated)
      await onSaved()
      onNotice('Settings saved')
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  const save = async () => {
    if (!form.formState.isDirty) return
    await saveMutation.mutateAsync(form.getValues()).catch(() => undefined)
  }

  const discard = () => {
    if (settingsQuery.data) form.reset(settingsQuery.data)
  }

  const updateGroup = <K extends keyof Settings>(group: K, value: Settings[K]) => {
    form.reset({ ...form.getValues(), [group]: value }, { keepDefaultValues: true })
  }

  const chooseDirectory = async (key: keyof Settings['directories']) => {
    const current = form.getValues(`directories.${key}`)
    try {
      const selected = await client.selectDirectory(current)
      if (selected) form.setValue(`directories.${key}`, selected, { shouldDirty: true })
    } catch (reason) {
      onError(errorMessage(reason))
    }
  }

  return {
    persisted: settingsQuery.data ?? null,
    draft,
    loading: settingsQuery.isLoading,
    busy: saveMutation.isPending,
    dirty: form.formState.isDirty,
    form,
    updateGroup,
    discard,
    save,
    chooseDirectory,
  }
}

export type SettingsController = ReturnType<typeof useSettingsController>
