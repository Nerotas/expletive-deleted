import type { InstallStatus } from '../types/domain'

const object = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value))

export function decodeInstallStatus(value: unknown, expectedId?: string): InstallStatus {
  const invalid = () => { throw Object.assign(new Error('The local service sent an invalid setup status.'), { code: 'protocol_error' }) }
  if (!object(value) || typeof value.install_id !== 'string' || !value.install_id
    || (expectedId !== undefined && value.install_id !== expectedId)
    || !['running', 'canceling', 'resolving', 'awaiting_resolution', 'completed', 'failed', 'cancelled'].includes(String(value.status))
    || typeof value.message !== 'string') return invalid()
  for (const field of ['completed_bytes', 'total_bytes', 'action_index', 'action_count']) {
    if (value[field] !== null && (typeof value[field] !== 'number' || !Number.isFinite(value[field]) || value[field] < 0)) return invalid()
  }
  if (value.status === 'awaiting_resolution') {
    const result = value.resolution
    if (!object(result) || result.status !== 'conflict' || !object(result.snapshot)
      || typeof result.snapshot.revision !== 'string' || !object(result.snapshot.settings)
      || !object(result.snapshot.settings.runtime) || !Array.isArray(result.conflicts)
      || !result.conflicts.every((conflict) => object(conflict) && typeof conflict.field === 'string')
      || !object(value.verified_values)
      || !Object.entries(value.verified_values).every(([key, path]) => ['runtime.ffmpeg_path', 'runtime.ffprobe_path', 'runtime.ytdlp_path', 'runtime.whisper_cache'].includes(key) && typeof path === 'string')) return invalid()
  }
  return value as InstallStatus
}
