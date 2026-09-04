import { useRef, useState } from 'react'
import {
  ArchiveIcon,
  ArrowDown,
  ArrowUp,
  CircleStop,
  FileText,
  FolderOpen,
  Play,
  RefreshCw,
  RotateCcw,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { LoadingRow } from '../../components/ui/LoadingRow'
import { PageHeading } from '../../components/ui/PageHeading'
import { StatusBadge } from '../../components/ui/StatusBadge'
import type {
  ArchiveItem,
  Capabilities,
  ImportResult,
  Job,
  JobEvent,
  JobSubmissionOptions,
  LibraryItem,
  Settings,
} from '../../types/domain'
import { fileName, formatBytes, formatEta } from '../../utils/format'
import type { QueueController } from './useQueue'
import './queue.css'

type QueuePageProps = {
  queue: QueueController
  settings: Settings | null
  capabilities: Capabilities | null
  onChangeFolder: () => void
  onReview: (source: string) => void
}
type View = 'queue' | 'archive'
type PurgeRequest = { source: string; label: string } | 'all' | null
type QueueRowModel = { item: LibraryItem; job?: Job; pendingJob?: Job }
type QueueFilter = 'all' | 'ready' | 'queued' | 'transcribed' | 'finished'
type QueueCategory = Exclude<QueueFilter, 'all'> | 'active' | 'other'
type QueueSort = 'queue' | 'name' | 'dateAdded' | 'status'
type SortDirection = 'ascending' | 'descending'
type QueueColumn = 'file' | 'dateAdded' | 'status' | 'queue' | 'progress' | 'actions'

const TERMINAL_STATUSES = new Set<Job['status']>(['completed', 'failed', 'cancelled', 'transcribed'])
const RUNNING_STATUSES = new Set<Job['status']>(['copying', 'transcribing', 'censoring', 'verifying'])

export function QueuePage({ queue, settings, capabilities, onChangeFolder, onReview }: QueuePageProps) {
  const [view, setView] = useState<View>('queue')
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set())
  const [droppedFiles, setDroppedFiles] = useState<File[] | null>(null)
  const [copying, setCopying] = useState(false)
  const [copyResults, setCopyResults] = useState<ImportResult[] | null>(null)
  const [purgeRequest, setPurgeRequest] = useState<PurgeRequest>(null)
  const dragDepth = useRef(0)
  const [dragActive, setDragActive] = useState(false)

  const mergedRows: QueueRowModel[] = queue.library.map((item) => {
    const sourceJobs = queue.jobs.filter((candidate) => candidate.source === item.source)
    return {
      item,
      job: sourceJobs.at(-1),
      pendingJob: sourceJobs.find((candidate) => !TERMINAL_STATUSES.has(candidate.status)),
    }
  })
  const copyRows = queue.jobs
    .filter((job) => job.mode === 'copy' && !TERMINAL_STATUSES.has(job.status))
    .filter((job) => !queue.library.some((item) => item.source === job.source))
    .map((job): QueueRowModel => ({
      item: {
        source: job.source,
        status: 'ready',
        date_added: new Date().toISOString(),
        transcript: null,
        output: null,
      },
      job,
      pendingJob: job,
    }))
  mergedRows.push(...copyRows)
  const selectableSources = mergedRows
    .filter(({ item, pendingJob }) => item.status === 'ready' && !pendingJob)
    .map(({ item }) => item.source)
  const selectableSet = new Set(selectableSources)
  const eligibleSelections = new Set(
    [...selectedSources].filter((source) => selectableSet.has(source)),
  )

  const receiveDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    dragDepth.current = 0
    setDragActive(false)
    const files = Array.from(event.dataTransfer.files)
    if (files.length) {
      setDroppedFiles(files)
      setCopyResults(null)
    }
  }
  const confirmCopy = async () => {
    if (!droppedFiles) return
    setCopying(true)
    setCopyResults(await queue.importSources(droppedFiles))
    setCopying(false)
  }
  const confirmPurge = async () => {
    if (!purgeRequest) return
    if (purgeRequest === 'all') await queue.purgeArchive()
    else await queue.purgeArchiveSource(purgeRequest.source)
    setPurgeRequest(null)
  }
  const toggleSelection = (source: string) => {
    setSelectedSources((current) => {
      // Polling may have changed eligibility since the last interaction.
      const next = new Set([...current].filter((candidate) => selectableSet.has(candidate)))
      if (next.has(source)) next.delete(source)
      else next.add(source)
      return next
    })
  }
  const submitSelection = async (mode: Job['mode'], orderedSources: string[]) => {
    const results = await queue.submitFiles(orderedSources, mode)
    const queued = new Set(
      results.filter((result) => result.status === 'queued').map((result) => result.source),
    )
    setSelectedSources((current) => new Set([...current].filter((source) => !queued.has(source))))
  }

  return <section
    className={`page queue-page ${dragActive ? 'drag-active' : ''}`}
    onDragEnter={(event) => {
      event.preventDefault()
      dragDepth.current += 1
      setDragActive(true)
    }}
    onDragOver={(event) => event.preventDefault()}
    onDragLeave={(event) => {
      event.preventDefault()
      dragDepth.current -= 1
      if (dragDepth.current <= 0) setDragActive(false)
    }}
    onDrop={receiveDrop}
  >
    <PageHeading
      title={view === 'queue' ? 'Queue' : 'Archive'}
      subtitle={view === 'queue'
        ? `${queue.library.length} supported ${queue.library.length === 1 ? 'file' : 'files'} in Ready`
        : `${queue.archive.length} original ${queue.archive.length === 1 ? 'file' : 'files'} retained in Processed`}
    >
      {view === 'queue' ? <>
        <button className="icon-button" title="Refresh queue" aria-label="Refresh queue" onClick={() => void queue.refresh()}>
          <RefreshCw size={18} />
        </button>
        <button className="icon-button" title="Open transcode folder" aria-label="Open transcode folder" onClick={() => void queue.openTranscodeFolder()}>
          <FolderOpen size={18} />
        </button>
        {queue.runningJob && <button className="button danger" onClick={() => void queue.cancelActive()}>
          <CircleStop size={17} />Cancel active job
        </button>}
      </> : <button className="button danger" disabled={queue.busy || !queue.archive.length} onClick={() => setPurgeRequest('all')}>
        <Trash2 size={17} />Purge all
      </button>}
    </PageHeading>

    <div className="queue-tabs" role="tablist" aria-label="Media storage views">
      <button role="tab" aria-selected={view === 'queue'} className={view === 'queue' ? 'selected' : ''} onClick={() => setView('queue')}>Queue</button>
      <button role="tab" aria-selected={view === 'archive'} className={view === 'archive' ? 'selected' : ''} onClick={() => setView('archive')}>Archive <span>{queue.archive.length}</span></button>
    </div>
    {view === 'queue' ? <QueueView
      mergedRows={mergedRows}
      queue={queue}
      settings={settings}
      capabilities={capabilities}
      selectedSources={eligibleSelections}
      onToggleSelection={toggleSelection}
      onSelectAll={(sources) => setSelectedSources(new Set(sources))}
      onClearSelection={() => setSelectedSources(new Set())}
      onSubmitSelection={submitSelection}
      onChangeFolder={onChangeFolder}
      onReview={onReview}
    /> : <ArchiveView
      items={queue.archive}
      busy={queue.busy}
      archivePath={settings?.directories.archive}
      queueIdle={queue.queueIdle}
      onRestore={queue.restoreArchiveSource}
      onPurge={(item) => setPurgeRequest({ source: item.source, label: fileName(item.source) })}
    />}
    {dragActive && <div className="drop-overlay" aria-hidden="true">
      <Upload size={38} />
      <strong>Drop files to add them to Ready</strong>
      <span>Your original files will stay where they are.</span>
    </div>}
    {droppedFiles && <CopyDialog
      files={droppedFiles}
      copying={copying}
      results={copyResults}
      readyPath={settings?.directories.input}
      onCancel={() => !copying && setDroppedFiles(null)}
      onConfirm={() => void confirmCopy()}
    />}
    {purgeRequest && <PurgeDialog
      request={purgeRequest}
      busy={queue.busy}
      onCancel={() => setPurgeRequest(null)}
      onConfirm={() => void confirmPurge()}
    />}
  </section>
}

function QueueView({
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
}) {
  const [filter, setFilter] = useState<QueueFilter>('all')
  const [sort, setSort] = useState<QueueSort>('queue')
  const [sortDirection, setSortDirection] = useState<SortDirection>('ascending')
  const [columnWidths, setColumnWidths] = useState<Record<QueueColumn, string>>({
    file: '18vw',
    dateAdded: '11vw',
    status: '8vw',
    queue: '9vw',
    progress: '10vw',
    actions: '18vw',
  })
  const selectedCount = selectedSources.size
  const processingUnavailable = !capabilities?.ready
  const batchDisabled = queue.busy || processingUnavailable || selectedCount === 0
  const queuedPositions = new Map(queue.queuedJobs.map((job, index) => [job.id, index + 1]))
  const rows = mergedRows.map((row) => {
    const active = Boolean(row.pendingJob && RUNNING_STATUSES.has(row.pendingJob.status))
    const queuePosition = row.pendingJob ? queuedPositions.get(row.pendingJob.id) : undefined
    const category: QueueCategory = active
      ? 'active'
      : queuePosition != null
        ? 'queued'
        : row.item.status === 'ready'
          ? 'ready'
          : row.item.status === 'transcribed'
            ? 'transcribed'
            : row.item.status === 'finished'
              ? 'finished'
              : 'other'
    return { ...row, active, queuePosition, category }
  })
  const categoryOrder = ['active', 'queued', 'ready', 'transcribed', 'finished', 'other']
  const sortedRows = [...rows].sort((left, right) => {
    const nameComparison = fileName(left.item.source).localeCompare(fileName(right.item.source), undefined, { numeric: true, sensitivity: 'base' })
    let comparison: number
    if (sort === 'name') comparison = nameComparison
    else if (sort === 'dateAdded') comparison = new Date(left.item.date_added).getTime() - new Date(right.item.date_added).getTime() || nameComparison
    else if (sort === 'status') {
      comparison = categoryOrder.indexOf(left.category) - categoryOrder.indexOf(right.category) || nameComparison
    } else {
      const leftRank = left.active ? 0 : left.queuePosition != null ? 1 : 2
      const rightRank = right.active ? 0 : right.queuePosition != null ? 1 : 2
      comparison = leftRank - rightRank
        || (left.queuePosition ?? Number.MAX_SAFE_INTEGER) - (right.queuePosition ?? Number.MAX_SAFE_INTEGER)
        || nameComparison
    }
    return sortDirection === 'ascending' ? comparison : -comparison
  })
  const activeRows = rows.filter((row) => row.active)
  const visibleRows = sortedRows.filter((row) => !row.active && (filter === 'all' || row.category === filter))
  const visibleSelectable = visibleRows
    .filter(({ item, pendingJob }) => item.status === 'ready' && !pendingJob)
    .map(({ item }) => item.source)
  const orderedSelection = sortedRows
    .map(({ item }) => item.source)
    .filter((source) => selectedSources.has(source))
  const counts = {
    all: rows.length,
    ready: rows.filter((row) => row.category === 'ready').length,
    queued: rows.filter((row) => row.category === 'queued').length,
    active: rows.filter((row) => row.category === 'active').length,
    transcribed: rows.filter((row) => row.category === 'transcribed').length,
    finished: rows.filter((row) => row.category === 'finished').length,
  }
  const setSortColumn = (column: QueueSort) => {
    if (column === sort) setSortDirection((direction) => direction === 'ascending' ? 'descending' : 'ascending')
    else {
      setSort(column)
      setSortDirection('ascending')
    }
  }
  const startColumnResize = (column: QueueColumn, event: React.PointerEvent<HTMLSpanElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidth = event.currentTarget.parentElement?.getBoundingClientRect().width ?? 110
    const resize = (moveEvent: PointerEvent) => {
      setColumnWidths((current) => ({ ...current, [column]: `${Math.max(110, startWidth + moveEvent.clientX - startX)}px` }))
    }
    const stopResize = () => {
      window.removeEventListener('pointermove', resize)
      window.removeEventListener('pointerup', stopResize)
    }
    window.addEventListener('pointermove', resize)
    window.addEventListener('pointerup', stopResize, { once: true })
  }
  const resizeHandle = (column: QueueColumn, label: string) => <span
    className="column-resizer"
    role="separator"
    aria-orientation="vertical"
    aria-label={`Resize ${label} column`}
    title={`Resize ${label} column`}
    onPointerDown={(event) => startColumnResize(column, event)}
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
  const queueRow = ({ item, job, pendingJob, active, queuePosition }: typeof rows[number]) => <QueueRow
    key={item.source}
    item={item}
    job={job}
    pendingJob={pendingJob}
    active={active}
    queuePosition={queuePosition}
    event={pendingJob ? queue.jobEvents[pendingJob.id] : job ? queue.jobEvents[job.id] : undefined}
    queueIdle={queue.queueIdle}
    processingReady={Boolean(capabilities?.ready)}
    busy={queue.busy}
    selected={selectedSources.has(item.source)}
    onToggleSelection={onToggleSelection}
    onReview={onReview}
    onArchive={queue.archiveSource}
    onOpenFile={queue.openFile}
    onRetry={queue.retryJob}
    onSubmit={queue.submitFile}
    onCancelRunning={queue.cancelActive}
    onRemoveQueued={queue.removeQueued}
  />
  const activeJobRow = ({ item, job, pendingJob }: typeof rows[number]) => {
    const activeJob = pendingJob ?? job
    if (!activeJob) return null
    const event = queue.jobEvents[activeJob.id]
    const detail = event?.fps
      ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}`
      : event?.eta_seconds != null
        ? `${formatEta(event.eta_seconds)} left`
        : 'Processing'
    return <div className="active-job-row" key={item.source}>
      <div className="file-cell">
        <span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span>
        <div><strong>{fileName(item.source)}</strong><small>{item.source}</small></div>
      </div>
      <time dateTime={item.date_added}>{new Date(item.date_added).toLocaleString()}</time>
      <div className="active-job-status"><StatusBadge status={activeJob.status} /><small>{detail}</small></div>
      <div className="progress-wrap"><div className={`progress-track progress-${activeJob.status}`}><span style={{ width: `${activeJob.progress_percent ?? 0}%` }} /></div><span>{Math.round(activeJob.progress_percent ?? 0)}%</span></div>
      <button className="active-cancel-action" disabled={queue.busy} title="Cancel this running job and keep the source file" onClick={() => void queue.cancelActive()}><CircleStop size={13} />Cancel job</button>
    </div>
  }

  return <>
    <div className="queue-summary">
      <Metric label="Ready" value={counts.ready} tone="neutral" />
      <Metric label="Queued" value={counts.queued} tone="queued" />
      <Metric label="Active" value={counts.active} tone="active" />
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
          className="button secondary"
          disabled={batchDisabled}
          title={processingUnavailable ? 'Complete setup before processing files' : selectedCount ? 'Create and verify transcripts for selected files' : 'Select one or more Ready files'}
          onClick={() => void onSubmitSelection('report_only', orderedSelection)}
        >
          <FileText size={16} />Queue transcript only
        </button>
        <button
          className="button primary"
          disabled={batchDisabled}
          title={processingUnavailable ? 'Complete setup before processing files' : selectedCount ? 'Transcribe, then create censored copies for selected files' : 'Select one or more Ready files'}
          onClick={() => void onSubmitSelection('censor', orderedSelection)}
        >
          <Play size={16} />Queue transcribe + transcode
        </button>
      </div>
    </div>

    <div className="table-frame queue-table-frame">
      <table className="queue-table">
        <colgroup>
          <col className="select-column" />
          <col style={{ width: columnWidths.file }} />
          <col style={{ width: columnWidths.dateAdded }} />
          <col style={{ width: columnWidths.status }} />
          <col style={{ width: columnWidths.queue }} />
          <col style={{ width: columnWidths.progress }} />
          <col style={{ width: columnWidths.actions }} />
        </colgroup>
        <thead><tr><th className="select-column"><span className="sr-only">Select</span></th>{sortHeader('name', 'File')}{sortHeader('dateAdded', 'Date added')}{sortHeader('status', 'Status')}{sortHeader('queue', 'Queue position')}<th className="resizable-header">Progress{resizeHandle('progress', 'Progress')}</th><th className="resizable-header">Actions{resizeHandle('actions', 'Actions')}</th></tr></thead>
        <tbody>
          {visibleRows.map(queueRow)}
          {!queue.loading && !visibleRows.length && <tr><td colSpan={7}><div className="empty-state">
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

function ArchiveView({ items, busy, archivePath, queueIdle, onRestore, onPurge }: { items: ArchiveItem[]; busy: boolean; archivePath?: string; queueIdle: boolean; onRestore: (source: string) => Promise<unknown>; onPurge: (item: ArchiveItem) => void }) {
  return <>
    <div className="archive-note">Archived originals are kept for inspection. Return one to Queue when you want it back in Ready; it will not overwrite an existing file.</div>
    <div className="table-frame archive-table-frame"><table className="archive-table">
      <thead><tr><th>Original</th><th>Archived</th><th>Size</th><th>Actions</th></tr></thead>
      <tbody>
        {items.map((item) => <tr key={item.source}>
          <td><div className="file-cell"><span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span><div><strong>{fileName(item.source)}</strong><small>{item.relative_path}</small></div></div></td>
          <td>{new Date(item.archived_at).toLocaleDateString()}</td>
          <td>{formatBytes(item.size_bytes)}</td>
          <td className="details-cell"><button disabled={busy || !queueIdle} title={!queueIdle ? 'Wait until the processing queue is idle before returning a file' : 'Move this original back to Ready'} onClick={() => void onRestore(item.source)}><RotateCcw size={13} />Return to Queue</button><button disabled={busy} onClick={() => onPurge(item)}><Trash2 size={13} />Delete permanently</button></td>
        </tr>)}
        {!items.length && <tr><td colSpan={4}><div className="empty-state"><ArchiveIcon size={28} /><strong>No archived originals</strong><span>After checking a finished file, choose Archive source to keep its original here.</span></div></td></tr>}
      </tbody>
    </table></div>
    <div className="path-bar"><ArchiveIcon size={16} /><span>{archivePath}</span></div>
  </>
}

function CopyDialog({ files, copying, results, readyPath, onCancel, onConfirm }: { files: File[]; copying: boolean; results: ImportResult[] | null; readyPath?: string; onCancel: () => void; onConfirm: () => void }) {
  const added = results?.filter((result) => result.status === 'added').length ?? 0
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="copy-dialog-title">
    <p className="eyebrow">Add files</p>
    <h2 id="copy-dialog-title">{copying ? 'Copying to Ready' : results ? 'Copy complete' : `Add ${files.length} ${files.length === 1 ? 'file' : 'files'} to Ready?`}</h2>
    {!results ? <p>They will be copied to <strong>{readyPath}</strong>. Your originals stay in their current folders.</p> : <>
      <p>{added ? `${added} ${added === 1 ? 'file was' : 'files were'} added to Ready.` : 'No files were added to Ready.'}</p>
      <ul className="copy-results">{results.map((result) => <li key={result.source} className={result.status}>{fileName(result.source)} — {result.status === 'added' ? 'Added to Ready' : result.detail}</li>)}</ul>
    </>}
    <div className="modal-actions">{results ? <button className="button primary" onClick={onCancel}>Done</button> : <>
      <button className="button secondary" disabled={copying} onClick={onCancel}>Cancel</button>
      <button className="button primary" disabled={copying} onClick={onConfirm}>{copying ? 'Copying to Ready…' : 'Add to Ready'}</button>
    </>}</div>
  </section></div>
}

function PurgeDialog({ request, busy, onCancel, onConfirm }: { request: Exclude<PurgeRequest, null>; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  const all = request === 'all'
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="purge-dialog-title">
    <p className="eyebrow">Permanent deletion</p>
    <h2 id="purge-dialog-title">{all ? 'Purge all archived originals?' : `Delete ${request.label}?`}</h2>
    <p>This permanently deletes {all ? 'every original in Processed' : 'this archived original'}. This cannot be undone.</p>
    <div className="modal-actions">
      <button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button className="button danger" disabled={busy} onClick={onConfirm}><Trash2 size={16} />Delete permanently</button>
    </div>
  </section></div>
}

function QueueRow({
  item,
  job,
  pendingJob,
  active,
  queuePosition,
  event,
  queueIdle,
  processingReady,
  busy,
  selected,
  onToggleSelection,
  onReview,
  onArchive,
  onOpenFile,
  onRetry,
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
  queueIdle: boolean
  processingReady: boolean
  busy: boolean
  selected: boolean
  onToggleSelection: (source: string) => void
  onReview: (source: string) => void
  onArchive: (source: string) => Promise<unknown>
  onOpenFile: (filePath: string) => Promise<void>
  onRetry: (job: Job) => Promise<unknown>
  onSubmit: (source: string, mode: Job['mode'], options?: JobSubmissionOptions) => Promise<void>
  onCancelRunning: () => Promise<unknown>
  onRemoveQueued: (job: Job) => Promise<void>
}) {
  const displayJob = pendingJob ?? job
  const status = displayJob?.status ?? item.status
  const statusLabel = status === 'queued' && displayJob
    ? ({ copy: 'Queued: copy', report_only: 'Queued: transcript', censor: 'Queued: transcode' } as const)[displayJob.mode]
    : undefined
  const percent = displayJob?.progress_percent
  const outputFile = item.status === 'finished' ? item.output : null
  const selectable = item.status === 'ready' && !pendingJob
  const processingDisabled = busy || !processingReady || Boolean(pendingJob)
  const transcribeDisabled = processingDisabled
  const combinedDisabled = processingDisabled
  const archiveDisabled = busy || !queueIdle || !['transcribed', 'finished'].includes(item.status)
  const processingReason = !processingReady
    ? 'Complete setup before processing this file'
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
      <span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span>
      <div><strong>{fileName(item.source)}</strong><small>{item.source}</small></div>
    </div></td>
    <td>{new Date(item.date_added).toLocaleString()}</td>
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
        {outputFile && <button className="play-action" title="Open the verified censored file in your default media player" onClick={() => void onOpenFile(outputFile)}><Play size={13} />Play</button>}
        {active && <button disabled={busy} title="Cancel this running job and keep the source file" onClick={() => void onCancelRunning()}><CircleStop size={13} />Cancel job</button>}
        {pendingJob?.status === 'queued' && <button disabled={busy} title="Remove this waiting job without cancelling the active job" onClick={() => void onRemoveQueued(pendingJob)}><X size={13} />Remove from queue</button>}
        <button
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
        ><FileText size={13} />{item.status === 'ready' ? 'Transcribe' : 'Retranscribe'}</button>
        <button
          className="censor-action"
          aria-label={item.status === 'finished' ? 'Retranscode' : 'Transcribe + Transcode'}
          disabled={combinedDisabled}
          title={processingReason ?? (item.status === 'finished'
            ? 'Replace the censored output; reuse the verified transcript when available'
            : 'Reuse a verified transcript when available, otherwise transcribe before censoring')}
          onClick={() => void onSubmit(
            item.source,
            'censor',
            item.status === 'finished' ? { overwrite_output: true } : undefined,
          )}
        ><Play size={13} />{item.status === 'finished' ? 'Retranscode' : 'Censor'}</button>
        <button
          className="archive-action"
          disabled={archiveDisabled}
          title={!['transcribed', 'finished'].includes(item.status) ? 'Archive is available after a verified transcript or output exists' : !queueIdle ? 'Wait until the processing queue is idle before archiving' : 'Move the verified source to Processed'}
          onClick={() => void onArchive(item.source)}
        ><ArchiveIcon size={13} />Archive</button>
        {job?.status === 'failed' && job.error?.retryable && !pendingJob && <button disabled={busy} onClick={() => void onRetry(job)}>Retry</button>}
      </div>
    </td>
  </tr>
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>
}
