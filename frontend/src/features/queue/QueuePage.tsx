import { useRef, useState } from 'react'
import { CircleStop, Download, FolderOpen, RefreshCw, Trash2, Upload } from 'lucide-react'
import { PageHeading } from '../../components/ui/PageHeading'
import type { Capabilities, ImportResult, Job, Settings } from '../../types/domain'
import { fileName } from '../../utils/format'
import { ArchiveView } from './ArchiveView'
import { CopyDialog, PurgeDialog, type PurgeRequest } from './MediaDialogs'
import { QueueView } from './QueueView'
import { YoutubeDialog, YoutubeAuthenticationDialog, type YoutubeAuthenticationRequest } from './YoutubeDialogs'
import { buildQueueRows, isBulkSelectable } from './queue-model'
import type { QueueController } from './useQueue'
import './queue.css'

type View = 'queue' | 'archive'

type QueuePageProps = {
  queue: QueueController
  settings: Settings | null
  capabilities: Capabilities | null
  onChangeFolder: () => void
  onReview: (source: string) => void
  onReviewInstall: (components: string[]) => void
}
export function QueuePage({ queue, settings, capabilities, onChangeFolder, onReview, onReviewInstall }: QueuePageProps) {
  const [view, setView] = useState<View>('queue')
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set())
  const [droppedFiles, setDroppedFiles] = useState<File[] | null>(null)
  const [copying, setCopying] = useState(false)
  const [copyResults, setCopyResults] = useState<ImportResult[] | null>(null)
  const [purgeRequest, setPurgeRequest] = useState<PurgeRequest>(null)
  const [youtubeDialogOpen, setYoutubeDialogOpen] = useState(false)
  const [youtubeAuthentication, setYoutubeAuthentication] = useState<YoutubeAuthenticationRequest | null>(null)
  const dragDepth = useRef(0)
  const [dragActive, setDragActive] = useState(false)
  const missingYoutubeComponents = [
    ...(!capabilities?.ytdlp ? ['ytdlp'] : []),
    ...(!capabilities?.js_runtime ? ['js_runtime'] : []),
  ]

  const mergedRows = buildQueueRows(queue.library, queue.jobs, queue.copyJobDates)
  const selectableSources = mergedRows
    .filter(({ item, job, pendingJob }) => isBulkSelectable(item, job, pendingJob))
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
      // Nested controls emit their own drag events; count them to avoid overlay flicker.
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
        <button className="button secondary" title={capabilities?.ytdlp ? 'Download an individual YouTube video to Ready' : 'yt-dlp is required for YouTube downloads'} onClick={() => setYoutubeDialogOpen(true)}>
          <Download size={16} />Download from YouTube
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
      onAuthenticationRequired={(job) => setYoutubeAuthentication({ url: job.url ?? job.source, retryId: job.id, cookiesUnavailable: job.error?.code === 'browser_cookies_unavailable' })}
      onReviewInstall={onReviewInstall}
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
    {youtubeDialogOpen && <YoutubeDialog
      available={Boolean(capabilities?.ytdlp)}
      busy={queue.busy}
      onCancel={() => setYoutubeDialogOpen(false)}
      onReviewSetup={() => {
        setYoutubeDialogOpen(false)
        onReviewInstall(missingYoutubeComponents)
      }}
      onConfirm={async (url, browser) => {
        const outcome = await queue.submitYoutubeDownload(url, undefined, browser)
        if (outcome.status === 'success') setYoutubeDialogOpen(false)
        if (outcome.status === 'authentication_required' || outcome.status === 'browser_cookies_unavailable') {
          setYoutubeDialogOpen(false)
          setYoutubeAuthentication({ url, cookiesUnavailable: outcome.status === 'browser_cookies_unavailable', diagnostic: outcome.diagnostic })
        }
      }}
    />}
    {youtubeAuthentication && <YoutubeAuthenticationDialog
      busy={queue.busy}
      cookiesUnavailable={youtubeAuthentication.cookiesUnavailable}
      diagnostic={youtubeAuthentication.diagnostic}
      onCancel={() => setYoutubeAuthentication(null)}
      onOpenYoutube={() => void queue.openExternal('https://www.youtube.com/')}
      onRetry={async (browser) => {
        const outcome = await queue.submitYoutubeDownload(youtubeAuthentication.url, youtubeAuthentication.retryId, browser)
        if (outcome.status === 'success') setYoutubeAuthentication(null)
        else setYoutubeAuthentication({ ...youtubeAuthentication, cookiesUnavailable: outcome.status === 'browser_cookies_unavailable', diagnostic: outcome.diagnostic })
        return outcome.status
      }}
    />}
  </section>
}
