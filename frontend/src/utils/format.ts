import type { JobStatus, LibraryStatus } from '../types/domain'

export function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

export function formatEta(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  return minutes ? `${minutes}m ${total % 60}s` : `${total}s`
}

export function statusLabel(status: LibraryStatus | JobStatus): string {
  return {
    ready: 'Ready',
    transcribed: 'Transcribed',
    finished: 'Finished',
    queued: 'Ready',
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

