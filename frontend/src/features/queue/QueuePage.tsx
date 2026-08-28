import { useRef, useState } from 'react'
import { ArchiveIcon, CircleStop, FolderOpen, Play, RefreshCw, Trash2, Upload } from 'lucide-react'
import { PageHeading } from '../../components/ui/PageHeading'
import { LoadingRow } from '../../components/ui/LoadingRow'
import { StatusBadge } from '../../components/ui/StatusBadge'
import type { ArchiveItem, Capabilities, ImportResult, Job, JobEvent, LibraryItem, Settings } from '../../types/domain'
import { fileName, formatBytes, formatEta } from '../../utils/format'
import type { QueueController } from './useQueue'
import './queue.css'

type QueuePageProps = { queue: QueueController; settings: Settings | null; capabilities: Capabilities | null; onChangeFolder: () => void; onReview: (source: string) => void }
type View = 'queue' | 'archive'
type PurgeRequest = { source: string; label: string } | 'all' | null

export function QueuePage({ queue, settings, capabilities, onChangeFolder, onReview }: QueuePageProps) {
  const [view, setView] = useState<View>('queue')
  const [droppedFiles, setDroppedFiles] = useState<File[] | null>(null)
  const [copying, setCopying] = useState(false)
  const [copyResults, setCopyResults] = useState<ImportResult[] | null>(null)
  const [purgeRequest, setPurgeRequest] = useState<PurgeRequest>(null)
  const dragDepth = useRef(0)
  const [dragActive, setDragActive] = useState(false)
  const mergedRows = queue.library.map((item) => ({ item, job: [...queue.jobs].reverse().find((candidate) => candidate.source === item.source) }))

  const receiveDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    dragDepth.current = 0
    setDragActive(false)
    const files = Array.from(event.dataTransfer.files)
    if (files.length) { setDroppedFiles(files); setCopyResults(null) }
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

  return <section className={`page queue-page ${dragActive ? 'drag-active' : ''}`} onDragEnter={(event) => { event.preventDefault(); dragDepth.current += 1; setDragActive(true) }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { event.preventDefault(); dragDepth.current -= 1; if (dragDepth.current <= 0) setDragActive(false) }} onDrop={receiveDrop}>
    <PageHeading title={view === 'queue' ? 'Queue' : 'Archive'} subtitle={view === 'queue' ? `${queue.library.length} supported ${queue.library.length === 1 ? 'file' : 'files'} in Ready` : `${queue.archive.length} original ${queue.archive.length === 1 ? 'file' : 'files'} retained in Processed`}>
      {view === 'queue' ? <><button className="icon-button" title="Refresh queue" onClick={() => void queue.refresh()}><RefreshCw size={18} /></button>{queue.activeJob && <button className="button danger" onClick={() => void queue.cancelActive()}><CircleStop size={17} />Cancel</button>}<button className="button primary" disabled={queue.busy || !capabilities?.ready || queue.library.every((item) => item.status === 'finished')} onClick={() => void queue.startBatch(settings?.processing.mode ?? 'censor')}><Play size={17} />Start batch</button></> : <button className="button danger" disabled={queue.busy || !queue.archive.length} onClick={() => setPurgeRequest('all')}><Trash2 size={17} />Purge all</button>}
    </PageHeading>

    <div className="queue-tabs" role="tablist" aria-label="Media storage views"><button role="tab" aria-selected={view === 'queue'} className={view === 'queue' ? 'selected' : ''} onClick={() => setView('queue')}>Queue</button><button role="tab" aria-selected={view === 'archive'} className={view === 'archive' ? 'selected' : ''} onClick={() => setView('archive')}>Archive <span>{queue.archive.length}</span></button></div>
    {view === 'queue' ? <QueueView mergedRows={mergedRows} queue={queue} settings={settings} onChangeFolder={onChangeFolder} onReview={onReview} /> : <ArchiveView items={queue.archive} busy={queue.busy} archivePath={settings?.directories.archive} onPurge={(item) => setPurgeRequest({ source: item.source, label: fileName(item.source) })} />}
    {dragActive && <div className="drop-overlay" aria-hidden="true"><Upload size={38} /><strong>Drop files to add them to Ready</strong><span>Your original files will stay where they are.</span></div>}
    {droppedFiles && <CopyDialog files={droppedFiles} copying={copying} results={copyResults} readyPath={settings?.directories.input} onCancel={() => !copying && setDroppedFiles(null)} onConfirm={() => void confirmCopy()} />}
    {purgeRequest && <PurgeDialog request={purgeRequest} busy={queue.busy} onCancel={() => setPurgeRequest(null)} onConfirm={() => void confirmPurge()} />}
  </section>
}

function QueueView({ mergedRows, queue, settings, onChangeFolder, onReview }: { mergedRows: { item: LibraryItem; job?: Job }[]; queue: QueueController; settings: Settings | null; onChangeFolder: () => void; onReview: (source: string) => void }) {
  return <><div className="queue-summary"><Metric label="Ready" value={mergedRows.filter(({ item, job }) => !job && item.status === 'ready').length} tone="neutral" /><Metric label="Active" value={queue.activeJob ? 1 : 0} tone="active" /><Metric label="Transcribed" value={mergedRows.filter(({ item, job }) => (job?.status ?? item.status) === 'transcribed').length} tone="warning" /><Metric label="Finished" value={mergedRows.filter(({ item, job }) => ['finished', 'completed'].includes(job?.status ?? item.status)).length} tone="success" /></div>
    <div className="table-frame"><table><thead><tr><th>File</th><th>Status</th><th>Progress</th><th>Details</th></tr></thead><tbody>{mergedRows.map(({ item, job }) => <QueueRow key={item.source} item={item} job={job} event={job ? queue.jobEvents[job.id] : undefined} activeJob={queue.activeJob} busy={queue.busy} onReview={onReview} onArchive={queue.archiveSource} onRetry={queue.retryJob} />)}{!queue.loading && !mergedRows.length && <tr><td colSpan={4}><div className="empty-state"><Upload size={28} /><strong>Drop media here to add it</strong><span>Files are copied to Ready; your originals stay where they are.</span></div></td></tr>}</tbody></table>{queue.loading && <LoadingRow>Reading local library</LoadingRow>}</div><div className="path-bar"><FolderOpen size={16} /><span>{settings?.directories.input}</span><button onClick={onChangeFolder}>Change folder</button></div></>
}

function ArchiveView({ items, busy, archivePath, onPurge }: { items: ArchiveItem[]; busy: boolean; archivePath?: string; onPurge: (item: ArchiveItem) => void }) {
  return <><div className="archive-note">Archived originals are kept for inspection and are never included in a new batch.</div><div className="table-frame"><table><thead><tr><th>Original</th><th>Archived</th><th>Size</th><th>Actions</th></tr></thead><tbody>{items.map((item) => <tr key={item.source}><td><div className="file-cell"><span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span><div><strong>{fileName(item.source)}</strong><small>{item.relative_path}</small></div></div></td><td>{new Date(item.archived_at).toLocaleDateString()}</td><td>{formatBytes(item.size_bytes)}</td><td className="details-cell"><button disabled={busy} onClick={() => onPurge(item)}><Trash2 size={13} />Delete permanently</button></td></tr>)}{!items.length && <tr><td colSpan={4}><div className="empty-state"><ArchiveIcon size={28} /><strong>No archived originals</strong><span>After checking a finished file, choose Archive source to keep its original here.</span></div></td></tr>}</tbody></table></div><div className="path-bar"><ArchiveIcon size={16} /><span>{archivePath}</span></div></>
}

function CopyDialog({ files, copying, results, readyPath, onCancel, onConfirm }: { files: File[]; copying: boolean; results: ImportResult[] | null; readyPath?: string; onCancel: () => void; onConfirm: () => void }) {
  const added = results?.filter((result) => result.status === 'added').length ?? 0
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="copy-dialog-title"><p className="eyebrow">Add files</p><h2 id="copy-dialog-title">{copying ? 'Copying to Ready' : results ? 'Copy complete' : `Add ${files.length} ${files.length === 1 ? 'file' : 'files'} to Ready?`}</h2>{!results ? <p>They will be copied to <strong>{readyPath}</strong>. Your originals stay in their current folders.</p> : <><p>{added ? `${added} ${added === 1 ? 'file was' : 'files were'} added to Ready.` : 'No files were added to Ready.'}</p><ul className="copy-results">{results.map((result) => <li key={result.source} className={result.status}>{fileName(result.source)} — {result.status === 'added' ? 'Added to Ready' : result.detail}</li>)}</ul></>}<div className="modal-actions">{results ? <button className="button primary" onClick={onCancel}>Done</button> : <><button className="button secondary" disabled={copying} onClick={onCancel}>Cancel</button><button className="button primary" disabled={copying} onClick={onConfirm}>{copying ? 'Copying to Ready…' : 'Add to Ready'}</button></>}</div></section></div>
}

function PurgeDialog({ request, busy, onCancel, onConfirm }: { request: Exclude<PurgeRequest, null>; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  const all = request === 'all'
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="purge-dialog-title"><p className="eyebrow">Permanent deletion</p><h2 id="purge-dialog-title">{all ? 'Purge all archived originals?' : `Delete ${request.label}?`}</h2><p>This permanently deletes {all ? 'every original in Processed' : 'this archived original'}. This cannot be undone.</p><div className="modal-actions"><button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button><button className="button danger" disabled={busy} onClick={onConfirm}><Trash2 size={16} />Delete permanently</button></div></section></div>
}

function QueueRow({ item, job, event, activeJob, busy, onReview, onArchive, onRetry }: { item: LibraryItem; job?: Job; event?: JobEvent; activeJob?: Job; busy: boolean; onReview: (source: string) => void; onArchive: (source: string) => Promise<void>; onRetry: (job: Job) => Promise<void> }) {
  const status = job?.status ?? item.status
  const percent = job?.progress_percent
  const detail = event?.fps ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}` : event?.eta_seconds != null ? `${formatEta(event.eta_seconds)} left` : job?.error?.detail ?? (status === 'transcribed' ? 'Report available' : ['completed', 'finished'].includes(status) ? 'Output verified' : activeJob?.id === job?.id ? 'Processing locally' : 'Waiting')
  const canArchive = item.status === 'transcribed' || item.status === 'finished'
  return <tr><td><div className="file-cell"><span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span><div><strong>{fileName(item.source)}</strong><small>{item.source}</small></div></div></td><td><StatusBadge status={status} /></td><td>{percent != null ? <div className="progress-wrap"><div className="progress-track"><span style={{ width: `${percent}%` }} /></div><span>{Math.round(percent)}%</span></div> : <span className="muted">—</span>}</td><td className="details-cell"><span>{detail}</span>{item.transcript && <button onClick={() => onReview(item.source)}>Review words</button>}{canArchive && <button disabled={busy || Boolean(activeJob)} onClick={() => void onArchive(item.source)}><ArchiveIcon size={13} />Archive source</button>}{job?.status === 'failed' && job.error?.retryable && <button onClick={() => void onRetry(job)}>Retry</button>}</td></tr>
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div> }
