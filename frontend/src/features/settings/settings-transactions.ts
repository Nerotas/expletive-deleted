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

export function applySettingChanges(settings: Settings, changes: FieldChange[]): Settings {
  const result = structuredClone(settings)
  for (const { field, value } of changes) {
    const [group, key] = field.split('.')
    ;(result[group as Exclude<keyof Settings, 'schema_version'>] as Record<string, SettingsValue>)[key] = value
  }
  return result
}
