import type { JobStatus } from '../../types/domain'

export function JobProgress({ status, percent }: { status: JobStatus; percent: number | null | undefined }) {
  const transcribing = status === 'transcribing'
  if (percent == null && !transcribing) return <span className="muted">—</span>

  return <div className="progress-wrap">
    <div
      className={`progress-track progress-${status}${percent == null ? ' progress-indeterminate' : ''}`}
      role="progressbar"
      aria-label={transcribing ? 'Transcription progress' : 'Job progress'}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent ?? undefined}
      aria-valuetext={percent == null ? 'Working; waiting for measured progress' : `${Math.round(percent)}% complete`}
    ><span style={{ width: percent == null ? '35%' : `${percent}%` }} /></div>
    {percent != null && <span>{Math.round(percent)}%</span>}
  </div>
}
