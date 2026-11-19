import type { JobEvent, JobStatus, LibraryStatus } from '../types/domain'

export function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

export function formatEta(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  return minutes ? `${minutes}m ${total % 60}s` : `${total}s`
}

export function formatJobProgress(event: JobEvent | undefined): string | undefined {
  if (event?.stage === 'transcribing' && event.speed != null) {
    const speed = `speed ${event.speed.toFixed(2)}x`
    return event.eta_seconds != null
      ? `${speed} · About ${formatEta(event.eta_seconds)} left`
      : `${event.message ?? 'Transcribing audio'} · ${speed}`
  }
  if (event?.fps) {
    return `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}`
  }
  if (event?.eta_seconds != null) return `${formatEta(event.eta_seconds)} left`
  return event?.message ?? undefined
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor(total % 3600 / 60)
  const remainingSeconds = total % 60
  const clock = `${minutes.toString().padStart(hours ? 2 : 1, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
  return hours ? `${hours}:${clock}` : clock
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = -1
  do {
    value /= 1024
    unit += 1
  } while (value >= 1024 && unit < units.length - 1)
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`
}

export function statusLabel(status: LibraryStatus | JobStatus): string {
  return {
    ready: 'Ready',
    unverified: 'Needs review',
    transcribed: 'Transcribed',
    finished: 'Finished',
    queued: 'Queued',
    downloading: 'Downloading',
    preparing: 'Preparing',
    copying: 'Copying',
    transcribing: 'Transcribing',
    censoring: 'Censoring',
    verifying: 'Verifying',
    completed: 'Finished',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }[status]
}

export function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}
