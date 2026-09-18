import { ArchiveIcon, CircleStop, FileText, Play, X } from 'lucide-react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import type { Job, JobEvent, JobSubmissionOptions, LibraryItem } from '../../types/domain'
import { fileName, formatEta } from '../../utils/format'
import { isBulkSelectable } from './queue-model'

export function QueueRow({
  item,
  job,
  pendingJob,
  active,
  queuePosition,
  event,
  processingReady,
  setupReason,
  busy,
  selected,
  onToggleSelection,
  onReview,
  onArchive,
  onOpenOutput,
  onRetry,
  onAuthenticationRequired,
  onDownloadJavaScriptRuntime,
  onSubmit,
  onCancelRunning,
  onRemoveQueued,
}: {
  item: LibraryItem
  job?: Job
  pendingJob?: Job
  active: boolean
  queuePosition?: number
  event?: JobEvent
  processingReady: boolean
  setupReason: string
  busy: boolean
  selected: boolean
  onToggleSelection: (source: string) => void
  onReview: (source: string) => void
  onArchive: (source: string) => Promise<unknown>
  onOpenOutput: (filePath: string) => Promise<void>
  onRetry: (job: Job) => Promise<unknown>
  onAuthenticationRequired: (job: Job) => void
  onDownloadJavaScriptRuntime: (job: Job) => void
  onSubmit: (source: string, mode: Job['mode'], options?: JobSubmissionOptions) => Promise<void>
  onCancelRunning: (job: Job) => Promise<unknown>
  onRemoveQueued: (job: Job) => Promise<void>
}) {
  // Historical success must not hide a newer queued or running action on the same file.
  const displayJob = pendingJob ?? job
  const status = displayJob?.status ?? item.status
  const statusLabel = status === 'queued' && displayJob
    ? ({ copy: 'Queued: copy', report_only: 'Queued: transcript', censor: 'Queued: transcode' } as const)[displayJob.mode]
    : undefined
  const percent = displayJob?.progress_percent
  const outputFile = item.status === 'finished' ? item.output : null
  const remote = displayJob?.source_type === 'youtube'
  const selectable = isBulkSelectable(item, job, pendingJob)
  const processingDisabled = busy || !processingReady || Boolean(pendingJob)
  const transcribeDisabled = processingDisabled
  const archiveDisabled = busy || Boolean(pendingJob) || !['transcribed', 'finished'].includes(item.status)
  const processingReason = !processingReady
    ? setupReason
    : pendingJob
      ? 'This file is already queued or processing'
      : busy
        ? 'Wait for the current queue action to finish'
        : undefined
  const detail = event?.fps
    ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}`
    : event?.eta_seconds != null
      ? `${formatEta(event.eta_seconds)} left`
      : displayJob?.error?.detail
        ?? (status === 'transcribed'
          ? 'Transcript verified'
          : ['completed', 'finished'].includes(status)
            ? 'Output verified'
            : status === 'queued'
              ? 'Waiting for earlier jobs'
              : pendingJob
                ? 'Processing'
                : 'Ready for an action')

  return <tr>
    <td className="select-column">
      <input
        type="checkbox"
        checked={selected}
        disabled={!selectable}
        aria-label={`Select ${fileName(item.source)}`}
        title={selectable ? `Select ${fileName(item.source)}` : 'Only unqueued Ready files can be selected'}
        onChange={() => onToggleSelection(item.source)}
      />
    </td>
    <td><div className="file-cell">
      <span className="file-icon">{remote ? 'YT' : fileName(item.source).split('.').pop()?.toUpperCase()}</span>
      <div><strong>{displayJob?.title ?? fileName(item.source)}</strong><small>{item.source}</small></div>
    </div></td>
    <td>{item.date_added ? new Date(item.date_added).toLocaleString() : <span className="muted">—</span>}</td>
    <td><StatusBadge status={status} label={statusLabel} /></td>
    <td className="position-cell">{active ? <strong>Active</strong> : queuePosition != null ? <span>#{queuePosition}</span> : <span className="muted">—</span>}</td>
    <td>{percent != null ? <div className="progress-wrap"><div className={`progress-track progress-${status}`}><span style={{ width: `${percent}%` }} /></div><span>{Math.round(percent)}%</span></div> : <span className="muted">—</span>}</td>
    <td className="actions-cell">
      <span className="row-detail">{detail}</span>
      {displayJob?.error?.diagnostic && <details className="job-diagnostic">
        <summary>Technical details</summary>
        <pre>{displayJob.error.diagnostic}</pre>
      </details>}
      <div className="row-actions" aria-label={`Actions for ${fileName(item.source)}`}>
        {item.transcript && <button className="review-action" onClick={() => onReview(item.source)}>Review words</button>}
        {outputFile && <button className="play-action" title="Open the verified censored file in your default media player" onClick={() => void onOpenOutput(item.source)}><Play size={13} />Play</button>}
        {active && displayJob && <button disabled={busy} title="Cancel this running job and keep the source file" onClick={() => void onCancelRunning(displayJob)}><CircleStop size={13} />Cancel job</button>}
        {pendingJob?.status === 'queued' && <button disabled={busy} title="Remove this waiting job without cancelling the active job" onClick={() => void onRemoveQueued(pendingJob)}><X size={13} />Remove from queue</button>}
        {!remote && item.status === 'transcribed' && <button
          className="censor-action"
          disabled={processingDisabled}
          title={processingReason ?? 'Create censored media from this verified transcript'}
          onClick={() => void onSubmit(item.source, 'censor')}
        ><Play size={13} />Censor</button>}
        {!remote && item.status === 'finished' && <button
          className="censor-action"
          disabled={processingDisabled}
          title={processingReason ?? 'Create a replacement censored copy from this verified transcript'}
          onClick={() => void onSubmit(item.source, 'censor', { overwrite_output: true })}
        ><Play size={13} />Recensor</button>}
        {!remote && <button
          className="transcribe-action"
          aria-label={item.status === 'ready' ? 'Transcribe only' : 'Retranscribe'}
          disabled={transcribeDisabled}
          title={processingReason ?? (item.status === 'ready'
            ? 'Create and verify a transcript, then stop'
            : 'Replace the existing transcript with a newly generated and verified transcript')}
          onClick={() => void onSubmit(
            item.source,
            'report_only',
            item.status === 'ready' ? undefined : { force_transcribe: true },
          )}
        ><FileText size={13} />{item.status === 'ready' ? 'Transcribe' : 'Retranscribe'}</button>}
        {!remote && <button
          className="archive-action"
          disabled={archiveDisabled}
          title={!['transcribed', 'finished'].includes(item.status) ? 'Archive is available after a verified transcript or output exists' : busy ? 'Wait for the current queue action to finish' : pendingJob ? 'This file is already queued or processing' : 'Move the verified source to Processed'}
          onClick={() => void onArchive(item.source)}
        ><ArchiveIcon size={13} />Archive</button>}
        {job?.status === 'failed' && (job.error?.code === 'authentication_required' || job.error?.code === 'browser_cookies_unavailable') && !pendingJob && <button disabled={busy} onClick={() => onAuthenticationRequired(job)}>Use browser session</button>}
        {job?.status === 'failed' && job.error?.code === 'javascript_runtime_required' && !pendingJob && <button disabled={busy} title="Download the approved JavaScript runtime yt-dlp needs to solve YouTube's challenge" onClick={() => onDownloadJavaScriptRuntime(job)}>Download JavaScript runtime</button>}
        {job?.status === 'failed' && job.error?.retryable && !['authentication_required', 'browser_cookies_unavailable', 'javascript_runtime_required'].includes(job.error.code) && !pendingJob && <button disabled={busy} onClick={() => void onRetry(job)}>Retry</button>}
      </div>
    </td>
  </tr>
}
