import { useState } from 'react'
import { ArrowDown, ArrowUp, CircleStop, FileText, FolderOpen, Play, Upload } from 'lucide-react'
import { LoadingRow } from '../../components/ui/LoadingRow'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { useColumnResize } from '../../hooks/use-column-resize'
import type { Capabilities, Job, Settings } from '../../types/domain'
import { fileName, formatEta } from '../../utils/format'
import { selectQueueRows, type QueueRowModel, type QueueFilter, type QueueSort, type SortDirection } from './queue-model'
import { QueueRow } from './QueueRow'
import type { QueueController } from './useQueue'

type QueueColumn = 'file' | 'length' | 'dateAdded' | 'status' | 'queue' | 'progress' | 'actions'
type DisplayRow = ReturnType<typeof selectQueueRows>['rows'][number]

export function QueueView({
  mergedRows,
  queue,
  settings,
  capabilities,
  selectedSources,
  onToggleSelection,
  onSelectAll,
  onClearSelection,
  onSubmitSelection,
  onChangeFolder,
  onReview,
  onAuthenticationRequired,
  onReviewInstall,
}: {
  mergedRows: QueueRowModel[]
  queue: QueueController
  settings: Settings | null
  capabilities: Capabilities | null
  selectedSources: Set<string>
  onToggleSelection: (source: string) => void
  onSelectAll: (sources: string[]) => void
  onClearSelection: () => void
  onSubmitSelection: (mode: Job['mode'], orderedSources: string[]) => Promise<void>
  onChangeFolder: () => void
  onReview: (source: string) => void
  onAuthenticationRequired: (job: Job) => void
  onReviewInstall: (components: string[]) => void
}) {
  const [filter, setFilter] = useState<QueueFilter>('all')
  const [sort, setSort] = useState<QueueSort>('queue')
  const [sortDirection, setSortDirection] = useState<SortDirection>('ascending')
  const { columnWidths, startColumnResize, resizeColumnBy } = useColumnResize<QueueColumn>({
    file: '18vw',
    length: '7vw',
    dateAdded: '11vw',
    status: '8vw',
    queue: '9vw',
    progress: '10vw',
    actions: '18vw',
  })
  const selectedCount = selectedSources.size
  const processingReady = capabilities?.processing_ready ?? capabilities?.ready ?? false
  const processingUnavailable = !processingReady
  const setupReason = capabilities?.app_runtime === 'invalid'
    ? 'Repair Expletive Deleted before processing files'
    : capabilities?.speech_model && capabilities.speech_model !== 'ready'
      ? 'Download the speech model before processing files'
      : 'Complete setup before processing files'
  const batchDisabled = queue.busy || processingUnavailable || selectedCount === 0
  const bulkMode: Job['mode'] = filter === 'transcribed' ? 'censor' : 'report_only'
  const bulkActionLabel = bulkMode === 'censor' ? 'Queue censor' : 'Queue transcript'
  const bulkActionTitle = processingUnavailable
    ? setupReason
    : selectedCount
      ? bulkMode === 'censor'
        ? 'Create censored copies from the verified transcripts for selected files'
        : 'Create and verify transcripts for selected files'
      : 'Select one or more files'
  const { activeRows, visibleRows, visibleSelectable, orderedSelection, counts } = selectQueueRows(
    mergedRows, queue.queuedJobs, filter, sort, sortDirection, selectedSources,
  )
  const setSortColumn = (column: QueueSort) => {
    if (column === sort) setSortDirection((direction) => direction === 'ascending' ? 'descending' : 'ascending')
    else {
      setSort(column)
      setSortDirection('ascending')
    }
  }
  const resizeHandle = (column: QueueColumn, label: string) => <span
    className="column-resizer"
    role="separator"
    tabIndex={0}
    aria-orientation="vertical"
    aria-label={`Resize ${label} column`}
    title={`Resize ${label} column`}
    onPointerDown={(event) => startColumnResize(column, event)}
    onKeyDown={(event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      event.preventDefault()
      const delta = event.key === 'ArrowLeft' ? -12 : 12
      const baseWidth = event.currentTarget.parentElement?.getBoundingClientRect().width ?? 110
      resizeColumnBy(column, baseWidth, delta)
    }}
  />
  const sortableColumns: Record<QueueSort, QueueColumn> = {
    name: 'file',
    dateAdded: 'dateAdded',
    status: 'status',
    queue: 'queue',
  }
  const sortHeader = (column: QueueSort, label: string) => <th className="resizable-header" aria-sort={sort === column ? sortDirection : 'none'}>
    <button
      className={`sort-header ${sort === column ? 'active' : ''}`}
      title={`Sort by ${label}${sort === column ? `, ${sortDirection}` : ''}`}
      onClick={() => setSortColumn(column)}
    >
      {label}
      {sort === column && (sortDirection === 'ascending' ? <ArrowUp size={13} /> : <ArrowDown size={13} />)}
    </button>
    {resizeHandle(sortableColumns[column], label)}
  </th>
  const queueRow = ({ item, job, pendingJob, active, queuePosition }: DisplayRow) => <QueueRow
    key={item.source}
    item={item}
    job={job}
    pendingJob={pendingJob}
    active={active}
    queuePosition={queuePosition}
    event={pendingJob ? queue.jobEvents[pendingJob.id] : job ? queue.jobEvents[job.id] : undefined}
    processingReady={processingReady}
    setupReason={setupReason}
    busy={queue.busy}
    selected={selectedSources.has(item.source)}
    onToggleSelection={onToggleSelection}
    onReview={onReview}
    onArchive={queue.archiveSource}
    onOpenOutput={queue.openOutput}
    onRetry={queue.retryJob}
    onAuthenticationRequired={onAuthenticationRequired}
    onDownloadJavaScriptRuntime={() => onReviewInstall(['js_runtime'])}
    onSubmit={queue.submitFile}
    onCancelRunning={queue.cancelJob}
    onRemoveQueued={queue.removeQueued}
  />
  const activeJobRow = ({ item, job, pendingJob }: DisplayRow) => {
    const activeJob = pendingJob ?? job
    if (!activeJob) return null
    const remote = activeJob.source_type === 'youtube'
    const event = queue.jobEvents[activeJob.id]
    const detail = event?.fps
      ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}`
      : event?.eta_seconds != null
        ? `${formatEta(event.eta_seconds)} left`
        : event?.message ?? 'Processing'
    return <div className="active-job-row" key={item.source}>
      <div className="file-cell">
        <span className="file-icon">{remote ? 'YT' : fileName(item.source).split('.').pop()?.toUpperCase()}</span>
        <div><strong>{activeJob.title ?? fileName(item.source)}</strong><small>{item.source}</small></div>
      </div>
      {item.date_added ? <time dateTime={item.date_added}>{new Date(item.date_added).toLocaleString()}</time> : <span className="muted">—</span>}
      <div className="active-job-status"><StatusBadge status={activeJob.status} /><small>{detail}</small></div>
      {activeJob.progress_percent != null ? <div className="progress-wrap"><div className={`progress-track progress-${activeJob.status}`}><span style={{ width: `${activeJob.progress_percent}%` }} /></div><span>{Math.round(activeJob.progress_percent)}%</span></div> : <span className="muted">—</span>}
      <button className="active-cancel-action" disabled={queue.busy} title="Cancel this running job and keep the source file" onClick={() => void queue.cancelJob(activeJob)}><CircleStop size={13} />Cancel job</button>
    </div>
  }

  return <>
    <div className="queue-summary">
      <Metric label="Ready" value={counts.ready} tone="neutral" />
      <Metric label="Queued" value={counts.queued} tone="queued" />
      <Metric label="Transcribed" value={counts.transcribed} tone="warning" />
      <Metric label="Finished" value={counts.finished} tone="success" />
    </div>

    {activeRows.map(activeJobRow)}

    <div className="table-controls">
      <div className="queue-filters" aria-label="Filter queue">
        {(['all', 'ready', 'queued', 'transcribed', 'finished'] as QueueFilter[]).map((value) => <button
          key={value}
          className={filter === value ? 'selected' : ''}
          aria-pressed={filter === value}
          onClick={() => setFilter(value)}
        >{value === 'all' ? 'All' : value[0].toUpperCase() + value.slice(1)} <span>{counts[value]}</span></button>)}
      </div>
    </div>

    <div className="batch-toolbar" aria-label="Selected file actions">
      <div className="selection-controls">
        <strong>{selectedCount} selected</strong>
        <button disabled={!visibleSelectable.length} onClick={() => onSelectAll(visibleSelectable)}>Select all shown</button>
        <button disabled={!selectedCount} onClick={onClearSelection}>Clear</button>
      </div>
      <div className="batch-actions">
        <button
          className={`button ${bulkMode === 'censor' ? 'primary' : 'secondary'}`}
          disabled={batchDisabled}
          title={bulkActionTitle}
          onClick={() => void onSubmitSelection(bulkMode, orderedSelection)}
        >
          {bulkMode === 'censor' ? <Play size={16} /> : <FileText size={16} />}{bulkActionLabel}
        </button>
      </div>
    </div>

    <div className="table-frame queue-table-frame">
      <table className="queue-table">
        <colgroup>
          <col className="select-column" />
          <col style={{ width: columnWidths.file }} />
          <col style={{ width: columnWidths.length }} />
          <col style={{ width: columnWidths.dateAdded }} />
          <col style={{ width: columnWidths.status }} />
          <col style={{ width: columnWidths.queue }} />
          <col style={{ width: columnWidths.progress }} />
          <col style={{ width: columnWidths.actions }} />
        </colgroup>
        <thead><tr><th className="select-column"><span className="sr-only">Select</span></th>{sortHeader('name', 'File')}<th className="resizable-header">Length{resizeHandle('length', 'Length')}</th>{sortHeader('dateAdded', 'Date added')}{sortHeader('status', 'Status')}{sortHeader('queue', 'Queue position')}<th className="resizable-header">Progress{resizeHandle('progress', 'Progress')}</th><th className="resizable-header">Actions{resizeHandle('actions', 'Actions')}</th></tr></thead>
        <tbody>
          {visibleRows.map(queueRow)}
          {!queue.loading && !visibleRows.length && <tr><td colSpan={8}><div className="empty-state">
            <Upload size={28} />
            <strong>{mergedRows.length ? `No ${filter} files` : 'Drop media here to add it'}</strong>
            <span>{mergedRows.length ? 'Choose another filter to see the rest of the queue.' : 'Files are copied to Ready; your originals stay where they are.'}</span>
          </div></td></tr>}
        </tbody>
      </table>
      {queue.loading && <LoadingRow>Reading local library</LoadingRow>}
    </div>
    <div className="path-bar"><FolderOpen size={16} /><span>{settings?.directories.input}</span><button onClick={onChangeFolder}>Change folder</button></div>
  </>
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>
}
