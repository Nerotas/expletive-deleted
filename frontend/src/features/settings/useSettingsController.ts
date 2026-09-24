import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { Settings, SettingsSnapshot, SettingsResult, SettingsField, FieldChange } from '../../types/domain'
import { settingChanges, settingValue, applySettingChanges } from './settings-transactions'
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
  const [baseline, setBaseline] = useState<SettingsSnapshot | null>(null)
  const saving = useRef(false)
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState<SettingsResult | null>(null)
  const choiceResolver = useRef<((choices: Partial<Record<SettingsField, boolean>> | null) => void) | null>(null)
  useEffect(() => () => choiceResolver.current?.(null), [])
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => client.getSettings(),
    staleTime: Number.POSITIVE_INFINITY,
  })
  const watchedDraft = useWatch({ control: form.control }) as Partial<Settings>
  const draft = watchedDraft.directories ? watchedDraft as Settings : null

  useEffect(() => {
    // Setup may refresh saved paths in the background; an edited form keeps its own draft.
    if (settingsQuery.data && !form.formState.isDirty && !saving.current) {
      setBaseline(settingsQuery.data)
      form.reset(settingsQuery.data.settings)
    }
  }, [form, settingsQuery.data])

  useEffect(() => {
    if (settingsQuery.error) onError(errorMessage(settingsQuery.error))
  }, [onError, settingsQuery.error])

  const saveDraft = async (nextSettings: Settings, wizardBase?: SettingsSnapshot): Promise<SettingsSnapshot | null> => {
    if (saving.current) return null
    const base = wizardBase ?? baseline
    if (!base) return null
    saving.current = true
    setBusy(true)
    const submitted = structuredClone(nextSettings)
    const formAtSubmit = structuredClone(form.getValues())
    let changes: FieldChange[] = settingChanges(base.settings, submitted)
    try {
      let result = wizardBase
        ? await client.patchSettings(base.revision, changes)
        : await client.updateSettings(submitted, base)
      while (result.status === 'conflict') {
        queryClient.setQueryData(['settings'], result.snapshot)
        setConflict(result)
        setBusy(false)
        const choices = await new Promise<Partial<Record<SettingsField, boolean>> | null>((resolve) => { choiceResolver.current = resolve })
        choiceResolver.current = null
        if (!choices) return null
        setBusy(true)
        changes = changes.map((change) => ({
          ...change,
          expected: settingValue(result.snapshot.settings, change.field),
          value: choices[change.field] === false ? settingValue(result.snapshot.settings, change.field) : change.value,
        }))
        result = await client.patchSettings(result.snapshot.revision, changes, true)
      }
      const updated = result.snapshot
      const laterEdits = settingChanges(formAtSubmit, form.getValues())
      setBaseline(updated)
      queryClient.setQueryData(['settings'], updated)
      form.reset(updated.settings)
      if (laterEdits.length) form.reset(applySettingChanges(updated.settings, laterEdits), { keepDefaultValues: true })
      await onSaved()
      onNotice('Settings saved')
      return updated
    } catch (reason) {
      onError(errorMessage(reason))
      return null
    } finally {
      setConflict(null)
      setBusy(false)
      saving.current = false
    }
  }

  const save = async () => {
    if (form.formState.isDirty) await saveDraft(form.getValues())
  }

  const discard = () => {
    if (saving.current) return
    if (settingsQuery.data) {
      setBaseline(settingsQuery.data)
      form.reset(settingsQuery.data.settings)
    }
  }

  const updateGroup = <K extends keyof Settings>(group: K, value: Settings[K]) => {
    // Compare edits with the last saved defaults so Discard and dirty tracking remain accurate.
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

  const chooseFfmpeg = async () => {
    try {
      const selected = await client.selectFile(form.getValues('runtime.ffmpeg_path') ?? undefined)
      if (!selected) return
      const inspected = await client.inspectExistingFfmpeg(selected)
      form.setValue('runtime', {
        ...form.getValues('runtime'),
        ffmpeg_path: inspected.ffmpeg_path,
        ffprobe_path: inspected.ffprobe_path,
      }, { shouldDirty: true })
    } catch (reason) {
      onError(errorMessage(reason))
    }
  }

  const chooseWhisperCache = async () => {
    try {
      const selected = await client.selectDirectory(
        form.getValues('runtime.whisper_cache') ?? undefined,
      )
      if (selected) form.setValue('runtime.whisper_cache', selected, { shouldDirty: true })
    } catch (reason) {
      onError(errorMessage(reason))
    }
  }

  return {
    persisted: settingsQuery.data?.settings ?? null,
    snapshot: baseline,
    conflict,
    cancelConflict: () => choiceResolver.current?.(null),
    resolveConflict: (choices: Partial<Record<SettingsField, boolean>>) => choiceResolver.current?.(choices),
    draft,
    loading: settingsQuery.isLoading,
    error: settingsQuery.error,
    busy,
    dirty: form.formState.isDirty,
    form,
    updateGroup,
    discard,
    save,
    saveDraft,
    chooseDirectory,
    chooseFfmpeg,
    chooseWhisperCache,
  }
}

export type SettingsController = ReturnType<typeof useSettingsController>
