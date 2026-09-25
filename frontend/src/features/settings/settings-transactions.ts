import type { FieldChange, Settings, SettingsField, SettingsValue } from '../../types/domain'

export function settingValue(settings: Settings, field: SettingsField): SettingsValue {
  const [group, key] = field.split('.')
  return (settings[group as Exclude<keyof Settings, 'schema_version'>] as Record<string, SettingsValue>)[key] ?? null
}

export function settingChanges(base: Settings, draft: Settings): FieldChange[] {
  return Object.entries(draft).flatMap(([group, values]) => typeof values === 'object'
    ? Object.entries(values).flatMap(([key, value]) => {
      const field = `${group}.${key}` as SettingsField
      const expected = settingValue(base, field)
      return expected === value ? [] : [{ field, expected, value: value as SettingsValue }]
    }) : [])
}

export type WizardProgress = Pick<Settings['onboarding'], 'last_step'> & Partial<Pick<Settings['onboarding'], 'completed'>>

// Only controls owned by the wizard belong in its patch. Runtime paths and
// preferences edited on the normal Settings page have independent owners.
const WIZARD_FIELDS: ReadonlySet<SettingsField> = new Set([
  'directories.input', 'directories.output', 'directories.archive', 'directories.transcripts',
  'censoring.stereo_method', 'processing.auto_censor_after_transcription',
  'processing.auto_transcode_youtube_downloads', 'source.archive_after_success',
])

export function wizardChanges(base: Settings, draft: Settings, progress: WizardProgress): FieldChange[] {
  const changes = settingChanges(base, draft).filter(({ field }) => WIZARD_FIELDS.has(field))
  // Progress is an explicit action even when it equals the baseline (Finish on
  // replay, or Continue after Back). A competing progress edit must be compared.
  changes.push({ field: 'onboarding.last_step', expected: base.onboarding.last_step, value: progress.last_step })
  if (progress.completed !== undefined) changes.push({ field: 'onboarding.completed', expected: base.onboarding.completed, value: progress.completed })
  return changes
}

export function applySettingChanges(settings: Settings, changes: FieldChange[]): Settings {
  const result = structuredClone(settings)
  for (const { field, value } of changes) {
    const [group, key] = field.split('.')
    ;(result[group as Exclude<keyof Settings, 'schema_version'>] as Record<string, SettingsValue>)[key] = value
  }
  return result
}

const FIELD_LABELS: Record<SettingsField, string> = {
  'directories.input': 'Ready / Input folder', 'directories.output': 'Finished / Output folder',
  'directories.archive': 'Processed / Archive folder', 'directories.transcripts': 'Transcripts folder',
  'processing.mode': 'Processing mode', 'processing.device': 'Processing device',
  'processing.auto_censor_after_transcription': 'Automatic censoring after transcription',
  'processing.auto_transcode_youtube_downloads': 'Automatic processing of YouTube downloads',
  'censoring.stereo_method': 'Censoring method', 'censoring.padding_before_ms': 'Padding before a word (ms)',
  'censoring.padding_after_ms': 'Padding after a word (ms)', 'audio.surround_output': 'Surround sound output',
  'video.mode': 'Video output', 'whisper.library': 'Transcription engine', 'whisper.model': 'Speech model',
  'source.archive_after_success': 'Archive originals after success', 'source.scan_subdirectories': 'Include subfolders',
  'onboarding.completed': 'Setup completed', 'onboarding.last_step': 'Saved setup step',
  'runtime.ffmpeg_path': 'FFmpeg path', 'runtime.ffprobe_path': 'FFprobe path',
  'runtime.whisper_cache': 'Whisper model folder', 'runtime.ytdlp_path': 'yt-dlp path',
}
export function settingsFieldLabel(field: SettingsField): string { return FIELD_LABELS[field] }
