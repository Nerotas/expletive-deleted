import {
  ArchiveIcon,
  CircleStop,
  FolderOpen,
  Play,
  RefreshCw,
} from 'lucide-react'
import { PageHeading } from '../../components/ui/PageHeading'
import { LoadingRow } from '../../components/ui/LoadingRow'
import { StatusBadge } from '../../components/ui/StatusBadge'
import type { Capabilities, Job, JobEvent, LibraryItem, Settings } from '../../types/domain'
import { fileName, formatEta } from '../../utils/format'
import type { QueueController } from './useQueue'
import './queue.css'

type QueuePageProps = {
  queue: QueueController
  settings: Settings | null
  capabilities: Capabilities | null
  onChangeFolder: () => void
  onReview: (source: string) => void
}

export function QueuePage({
  queue,
  settings,
  capabilities,
  onChangeFolder,
  onReview,
}: QueuePageProps) {
  const mergedRows = queue.library.map((item) => ({
    item,
    job: [...queue.jobs].reverse().find((candidate) => candidate.source === item.source),
  }))

  return (
    <section className="page queue-page">
      <PageHeading
        title="Queue"
        subtitle={`${queue.library.length} supported ${queue.library.length === 1 ? 'file' : 'files'} in Ready`}
      >
        <button className="icon-button" title="Refresh queue" onClick={() => void queue.refresh()}>
          <RefreshCw size={18} />
        </button>
        {queue.activeJob && (
          <button className="button danger" onClick={() => void queue.cancelActive()}>
            <CircleStop size={17} />Cancel
          </button>
        )}
        <button
          className="button primary"
          disabled={
            queue.busy
            || !capabilities?.ready
            || queue.library.every((item) => item.status === 'finished')
          }
          onClick={() => void queue.startBatch(settings?.processing.mode ?? 'censor')}
        >
          <Play size={17} />Start batch
        </button>
      </PageHeading>

      <div className="queue-summary">
        <Metric
          label="Ready"
          value={mergedRows.filter(({ item, job }) => !job && item.status === 'ready').length}
          tone="neutral"
        />
        <Metric label="Active" value={queue.activeJob ? 1 : 0} tone="active" />
        <Metric
          label="Transcribed"
          value={mergedRows.filter(({ item, job }) =>
            (job?.status ?? item.status) === 'transcribed').length}
          tone="warning"
        />
        <Metric
          label="Finished"
          value={mergedRows.filter(({ item, job }) =>
            ['finished', 'completed'].includes(job?.status ?? item.status)).length}
          tone="success"
        />
      </div>

      <div className="table-frame">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {mergedRows.map(({ item, job }) => (
              <QueueRow
                key={item.source}
                item={item}
                job={job}
                event={job ? queue.jobEvents[job.id] : undefined}
                activeJob={queue.activeJob}
                busy={queue.busy}
                onReview={onReview}
                onArchive={queue.archiveSource}
                onRetry={queue.retryJob}
              />
            ))}
            {!queue.loading && mergedRows.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <div className="empty-state">
                    <FolderOpen size={28} />
                    <strong>No media in Ready</strong>
                    <span>Add a supported audio or video file to the configured input folder.</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {queue.loading && <LoadingRow>Reading local library</LoadingRow>}
      </div>

      <div className="path-bar">
        <FolderOpen size={16} />
        <span>{settings?.directories.input}</span>
        <button onClick={onChangeFolder}>Change folder</button>
      </div>
    </section>
  )
}

type QueueRowProps = {
  item: LibraryItem
  job?: Job
  event?: JobEvent
  activeJob?: Job
  busy: boolean
  onReview: (source: string) => void
  onArchive: (source: string) => Promise<void>
  onRetry: (job: Job) => Promise<void>
}

function QueueRow({
  item,
  job,
  event,
  activeJob,
  busy,
  onReview,
  onArchive,
  onRetry,
}: QueueRowProps) {
  const status = job?.status ?? item.status
  const percent = job?.progress_percent
  const detail = event?.fps
    ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}`
    : event?.eta_seconds != null
      ? `${formatEta(event.eta_seconds)} left`
      : job?.error?.detail
        ?? (status === 'transcribed'
          ? 'Report available'
          : ['completed', 'finished'].includes(status)
            ? 'Output verified'
            : activeJob?.id === job?.id
              ? 'Processing locally'
              : 'Waiting')
  const canArchive = item.status === 'transcribed' || item.status === 'finished'

  return (
    <tr>
      <td>
        <div className="file-cell">
          <span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span>
          <div>
            <strong>{fileName(item.source)}</strong>
            <small>{item.source}</small>
          </div>
        </div>
      </td>
      <td><StatusBadge status={status} /></td>
      <td>
        {percent != null ? (
          <div className="progress-wrap">
            <div className="progress-track"><span style={{ width: `${percent}%` }} /></div>
            <span>{Math.round(percent)}%</span>
          </div>
        ) : <span className="muted">—</span>}
      </td>
      <td className="details-cell">
        <span>{detail}</span>
        {item.transcript && <button onClick={() => onReview(item.source)}>Review words</button>}
        {canArchive && (
          <button
            disabled={busy || Boolean(activeJob)}
            onClick={() => void onArchive(item.source)}
          >
            <ArchiveIcon size={13} />Archive source
          </button>
        )}
        {job?.status === 'failed' && job.error?.retryable && (
          <button onClick={() => void onRetry(job)}>Retry</button>
        )}
      </td>
    </tr>
  )
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
