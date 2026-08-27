import { startTransition, useCallback, useEffect, useState, type ReactNode } from 'react'
import { AlertCircle, Check, CircleStop, FolderOpen, ListVideo, LoaderCircle, Play, RefreshCw, RotateCcw, Save, Settings as SettingsIcon, ShieldCheck } from 'lucide-react'
import './App.css'
import './queue-details.css'

type Page = 'queue' | 'settings'
type LibraryStatus = 'ready' | 'transcribed' | 'finished'
type JobStatus = 'queued' | 'transcribing' | 'transcribed' | 'censoring' | 'verifying' | 'completed' | 'failed' | 'cancelled'
type LibraryItem = { source: string; status: LibraryStatus; transcript: string | null; output: string | null }
type JobError = { code: string; message: string; detail: string | null; retryable: boolean }
type Job = { id: string; source: string; mode: 'report_only' | 'censor'; status: JobStatus; progress_percent: number | null; error: JobError | null }
type JobEvent = { event: string; job_id: string; sequence: number; stage: JobStatus | null; percent: number | null; eta_seconds: number | null; fps: number | null; message: string | null }
type Capabilities = { ready: boolean; ffmpeg: boolean; ffprobe: boolean; whisper: boolean; model_large_v3: boolean; whisper_device: string; video_encoders: string[] }
type DictionaryInfo = { words_path: string; words_count: number; exclusions_path: string; exclusions_count: number }
type Settings = {
  schema_version: number
  directories: { input: string; output: string; archive: string; transcripts: string }
  processing: { mode: 'report_only' | 'censor'; device: 'auto' | 'cpu' | 'cuda' }
  censoring: { stereo_method: 'drop_audio' | 'karaoke'; padding_before_ms: number; padding_after_ms: number }
  audio: { surround_output: 'preserve_5_1' | 'downmix_stereo' }
  video: { mode: 'h264' | 'preserve_source' }
  whisper: { model: 'large-v3' }
  source: { archive_after_success: boolean }
  runtime: { ffmpeg_path: string | null; ffprobe_path: string | null; whisper_cache: string | null }
}
type InstallPlan = { plan_id: string; actions: Array<{ id: string; description: string; source_name: string; source_url: string; estimated_download_bytes: number | null }> }

const invoke = <T,>(method: Parameters<typeof window.profanityCensor.invoke>[0], params?: Record<string, unknown>) => window.profanityCensor.invoke<T>(method, params)
const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path
const formatEta = (seconds: number) => { const total = Math.max(0, Math.round(seconds)); const minutes = Math.floor(total / 60); return minutes ? `${minutes}m ${total % 60}s` : `${total}s` }
const statusLabel = (status: LibraryStatus | JobStatus) => ({ ready: 'Ready', transcribed: 'Transcribed', finished: 'Finished', queued: 'Ready', transcribing: 'Transcribing', censoring: 'Censoring', verifying: 'Verifying', completed: 'Finished', failed: 'Failed', cancelled: 'Cancelled' })[status]

function App() {
  const [page, setPage] = useState<Page>('queue')
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [library, setLibrary] = useState<LibraryItem[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [jobEvents, setJobEvents] = useState<Record<string, JobEvent>>({})
  const [dictionary, setDictionary] = useState<DictionaryInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [installPlan, setInstallPlan] = useState<InstallPlan | null>(null)

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [nextSettings, nextLibrary, nextJobs] = await Promise.all([
        invoke<Settings>('settings.get'), invoke<LibraryItem[]>('library.list'), invoke<Job[]>('jobs.list'),
      ])
      startTransition(() => { setSettings(nextSettings); setLibrary(nextLibrary); setJobs(nextJobs) })
      const eventGroups = await Promise.all(nextJobs.map((job) => invoke<JobEvent[]>('jobs.events', { job_id: job.id })))
      setJobEvents(Object.fromEntries(eventGroups.flatMap((events) => events.length ? [[events.at(-1)!.job_id, events.at(-1)!]] : [])))
      if (!quiet) {
        const [nextCapabilities, nextDictionary] = await Promise.all([invoke<Capabilities>('capabilities.get'), invoke<DictionaryInfo>('dictionary.get')])
        setCapabilities(nextCapabilities)
        setDictionary(nextDictionary)
      }
      setError(null)
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { if (!quiet) setLoading(false) }
  }, [])

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0)
    const timer = window.setInterval(() => void refresh(true), 1500)
    return () => { window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refresh])

  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(null); setNotice(null)
    try { await action(); await refresh(true) }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }

  const saveSettings = async () => {
    if (!settings) return
    await run(async () => { const updated = await invoke<Settings>('settings.update', { settings }); setSettings(updated); setNotice('Settings saved') })
  }
  const startBatch = async () => {
    const pending = library.filter((item) => item.status !== 'finished')
    await run(async () => { for (const item of pending) await invoke<Job>('jobs.submit', { source: item.source, mode: settings?.processing.mode ?? 'censor' }); setNotice(`${pending.length} ${pending.length === 1 ? 'file' : 'files'} queued`) })
  }
  const cancelActive = async () => {
    const active = jobs.find((job) => !['completed', 'failed', 'cancelled', 'transcribed'].includes(job.status)); if (!active) return
    await run(async () => { await invoke<Job>('jobs.cancel', { job_id: active.id }); setNotice('Cancellation requested') })
  }
  const reviewPlan = async (components: string[]) => run(async () => setInstallPlan(await invoke<InstallPlan>('dependencies.plan', { components })))
  const approveModelPlan = async () => {
    if (!installPlan) return
    await run(async () => { await invoke('dependencies.install', { plan_id: installPlan.plan_id }); setInstallPlan(null); setCapabilities(await invoke<Capabilities>('capabilities.get')); setNotice('Whisper large-v3 installed and verified') })
  }
  const chooseDirectory = async (key: keyof Settings['directories']) => {
    if (!settings) return
    const selected = await window.profanityCensor.selectDirectory(settings.directories[key])
    if (selected) setSettings({ ...settings, directories: { ...settings.directories, [key]: selected } })
  }
  const retryJob = async (job: Job) => run(async () => { await invoke<Job>('jobs.submit', { source: job.source, mode: job.mode }); setNotice(`${fileName(job.source)} queued again`) })

  const mergedRows = library.map((item) => ({ item, job: [...jobs].reverse().find((candidate) => candidate.source === item.source) }))
  const activeJob = jobs.find((job) => !['completed', 'failed', 'cancelled', 'transcribed'].includes(job.status))

  return <div className="app-shell">
    <header className="app-header">
      <div className="brand-lockup"><div className="brand-mark" aria-hidden="true"><span /></div><div><strong>Profanity Censor</strong><small>Local media processing</small></div></div>
      <nav className="top-nav" aria-label="Application pages"><button className={page === 'queue' ? 'active' : ''} onClick={() => setPage('queue')}><ListVideo size={17} />Queue</button><button className={page === 'settings' ? 'active' : ''} onClick={() => setPage('settings')}><SettingsIcon size={17} />Settings</button></nav>
      <div className={`runtime-pill ${capabilities?.ready ? 'ready' : 'attention'}`}>{capabilities?.ready ? <ShieldCheck size={16} /> : <AlertCircle size={16} />}{capabilities?.ready ? 'System ready' : 'Setup required'}</div>
    </header>
    <main>
      {error && <div className="alert error"><AlertCircle size={18} /><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}
      {notice && <div className="alert success"><Check size={18} /><span>{notice}</span><button onClick={() => setNotice(null)}>Dismiss</button></div>}
      {!loading && capabilities && !capabilities.ready && <section className="setup-band"><div><span className="eyebrow">Required component</span><h2>Finish local setup</h2><p>Processing stays on this computer. Review each source before anything is downloaded.</p></div><div className="setup-items"><SetupItem label="FFmpeg + FFprobe" ready={capabilities.ffmpeg && capabilities.ffprobe} action={!(capabilities.ffmpeg && capabilities.ffprobe) ? () => reviewPlan(['ffmpeg']) : undefined} /><SetupItem label="Speech recognition" ready={capabilities.whisper} action={!capabilities.whisper ? () => reviewPlan(['python']) : undefined} /><SetupItem label="Whisper large-v3" ready={capabilities.model_large_v3} action={!capabilities.model_large_v3 ? () => reviewPlan(['whisper_model']) : undefined} /></div></section>}
      {installPlan && <InstallDialog plan={installPlan} busy={busy} onCancel={() => setInstallPlan(null)} onApprove={approveModelPlan} />}
      {page === 'queue' ? <section className="page queue-page">
        <PageHeading title="Queue" subtitle={`${library.length} supported ${library.length === 1 ? 'file' : 'files'} in Ready`}><button className="icon-button" title="Refresh queue" onClick={() => void refresh()}><RefreshCw size={18} /></button>{activeJob && <button className="button danger" onClick={cancelActive}><CircleStop size={17} />Cancel</button>}<button className="button primary" disabled={busy || !capabilities?.ready || library.every((item) => item.status === 'finished')} onClick={startBatch}><Play size={17} />Start batch</button></PageHeading>
        <div className="queue-summary"><Metric label="Ready" value={mergedRows.filter(({ item, job }) => !job && item.status === 'ready').length} tone="neutral" /><Metric label="Active" value={activeJob ? 1 : 0} tone="active" /><Metric label="Transcribed" value={mergedRows.filter(({ item, job }) => (job?.status ?? item.status) === 'transcribed').length} tone="warning" /><Metric label="Finished" value={mergedRows.filter(({ item, job }) => ['finished', 'completed'].includes(job?.status ?? item.status)).length} tone="success" /></div>
        <div className="table-frame"><table><thead><tr><th>File</th><th>Status</th><th>Progress</th><th>Details</th></tr></thead><tbody>{mergedRows.map(({ item, job }) => { const status = job?.status ?? item.status; const percent = job?.progress_percent; const event = job ? jobEvents[job.id] : undefined; const detail = event?.fps ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}` : event?.eta_seconds != null ? `${formatEta(event.eta_seconds)} left` : job?.error?.detail ?? (status === 'transcribed' ? 'Report available' : ['completed', 'finished'].includes(status) ? 'Output verified' : activeJob?.id === job?.id ? 'Processing locally' : 'Waiting'); return <tr key={item.source}><td><div className="file-cell"><span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span><div><strong>{fileName(item.source)}</strong><small>{item.source}</small></div></div></td><td><StatusBadge status={status} /></td><td>{percent != null ? <div className="progress-wrap"><div className="progress-track"><span style={{ width: `${percent}%` }} /></div><span>{Math.round(percent)}%</span></div> : <span className="muted">—</span>}</td><td className="details-cell"><span>{detail}</span>{job?.status === 'failed' && job.error?.retryable && <button onClick={() => retryJob(job)}>Retry</button>}</td></tr> })}{!loading && mergedRows.length === 0 && <tr><td colSpan={4}><div className="empty-state"><FolderOpen size={28} /><strong>No media in Ready</strong><span>Add a supported audio or video file to the configured input folder.</span></div></td></tr>}</tbody></table>{loading && <div className="loading-row"><LoaderCircle className="spin" size={20} />Reading local library</div>}</div>
        <div className="path-bar"><FolderOpen size={16} /><span>{settings?.directories.input}</span><button onClick={() => setPage('settings')}>Change folder</button></div>
      </section> : settings ? <SettingsPage settings={settings} setSettings={setSettings} chooseDirectory={chooseDirectory} save={saveSettings} busy={busy} capabilities={capabilities} dictionary={dictionary} /> : <div className="loading-row"><LoaderCircle className="spin" size={20} />Loading settings</div>}
    </main>
  </div>
}

function PageHeading({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <div className="page-heading"><div><span className="eyebrow">Workspace</span><h1>{title}</h1><p>{subtitle}</p></div><div className="heading-actions">{children}</div></div> }
function SetupItem({ label, ready, action }: { label: string; ready: boolean; action?: () => void }) { return <div className="setup-item">{ready ? <Check size={17} /> : <AlertCircle size={17} />}<span>{label}</span><strong>{ready ? 'Ready' : 'Missing'}</strong>{action && <button onClick={action}>Review download</button>}</div> }
function InstallDialog({ plan, busy, onCancel, onApprove }: { plan: InstallPlan; busy: boolean; onCancel: () => void; onApprove: () => void }) { const action = plan.actions[0]; const size = action.estimated_download_bytes ? `${(action.estimated_download_bytes / 1024 ** 3).toFixed(1)} GB estimated` : 'Size determined by source'; return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="install-title"><span className="eyebrow">Review required</span><h2 id="install-title">Install required component</h2><p>{action.description}</p><dl><div><dt>Source</dt><dd>{action.source_name}</dd></div><div><dt>Download</dt><dd>{size}</dd></div><div><dt>Approval ID</dt><dd><code>{plan.plan_id}</code></dd></div></dl><div className="modal-actions"><button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button><button className="button primary" disabled={busy} onClick={onApprove}>{busy ? <LoaderCircle className="spin" size={17} /> : <ShieldCheck size={17} />}{busy ? 'Installing and verifying' : 'Approve and install'}</button></div></section></div> }
function Metric({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div> }
function StatusBadge({ status }: { status: LibraryStatus | JobStatus }) { return <span className={`status-badge status-${status}`}>{['transcribing', 'censoring', 'verifying'].includes(status) && <LoaderCircle className="spin" size={13} />}{statusLabel(status)}</span> }

function SettingsPage({ settings, setSettings, chooseDirectory, save, busy, capabilities, dictionary }: { settings: Settings; setSettings: (value: Settings) => void; chooseDirectory: (key: keyof Settings['directories']) => void; save: () => void; busy: boolean; capabilities: Capabilities | null; dictionary: DictionaryInfo | null }) {
  const setGroup = <K extends keyof Settings>(group: K, value: Settings[K]) => setSettings({ ...settings, [group]: value })
  return <section className="page settings-page"><PageHeading title="Settings" subtitle="Persistent preferences for local processing"><button className="button secondary" onClick={() => window.location.reload()}><RotateCcw size={17} />Discard</button><button className="button primary" disabled={busy} onClick={save}><Save size={17} />Save changes</button></PageHeading><div className="settings-layout">
    <SettingsSection title="Directories" description="User-owned working folders">{(Object.keys(settings.directories) as Array<keyof Settings['directories']>).map((key) => <label className="path-field" key={key}><span>{({ input: 'Ready / Input', output: 'Finished / Output', archive: 'Processed / Archive', transcripts: 'Transcripts' })[key]}</span><div><input value={settings.directories[key]} onChange={(event) => setGroup('directories', { ...settings.directories, [key]: event.target.value })} /><button className="icon-button" title={`Choose ${key} directory`} onClick={() => chooseDirectory(key)}><FolderOpen size={17} /></button></div></label>)}</SettingsSection>
    <SettingsSection title="Processing" description="Choose the workflow and compute device"><Field label="Mode"><Segmented value={settings.processing.mode} options={[['report_only', 'Report only'], ['censor', 'Censor media']]} onChange={(mode) => setGroup('processing', { ...settings.processing, mode })} /></Field><Field label="Device"><select value={settings.processing.device} onChange={(event) => setGroup('processing', { ...settings.processing, device: event.target.value as Settings['processing']['device'] })}><option value="auto">Automatic ({capabilities?.whisper_device ?? 'detecting'})</option><option value="cpu">CPU</option><option value="cuda">CUDA</option></select></Field></SettingsSection>
    <SettingsSection title="Censoring" description="Audio treatment and interval timing"><Field label="Stereo method"><Segmented value={settings.censoring.stereo_method} options={[['drop_audio', 'Drop audio'], ['karaoke', 'Karaoke']]} onChange={(stereo_method) => setGroup('censoring', { ...settings.censoring, stereo_method })} /></Field><div className="field-pair"><Field label="Before word"><NumberInput value={settings.censoring.padding_before_ms} onChange={(padding_before_ms) => setGroup('censoring', { ...settings.censoring, padding_before_ms })} /></Field><Field label="After word"><NumberInput value={settings.censoring.padding_after_ms} onChange={(padding_after_ms) => setGroup('censoring', { ...settings.censoring, padding_after_ms })} /></Field></div></SettingsSection>
    <SettingsSection title="Output" description="Audio layout, video handling, and source safety"><Field label="Surround audio"><Segmented value={settings.audio.surround_output} options={[['preserve_5_1', 'Preserve 5.1'], ['downmix_stereo', 'Downmix to stereo']]} onChange={(surround_output) => setGroup('audio', { surround_output })} /></Field><Field label="Video"><Segmented value={settings.video.mode} options={[['h264', 'H.264'], ['preserve_source', 'Preserve source']]} onChange={(mode) => setGroup('video', { mode })} /></Field><label className="toggle-row"><div><strong>Archive original after success</strong><span>Never moves source files after failure or cancellation.</span></div><input type="checkbox" checked={settings.source.archive_after_success} onChange={(event) => setGroup('source', { archive_after_success: event.target.checked })} /></label></SettingsSection>
    <SettingsSection title="Whisper" description="Accuracy is fixed for reliable censor timing"><div className="locked-setting"><ShieldCheck size={18} /><div><strong>large-v3</strong><span>Required model · smaller models are unsupported</span></div><span className="lock-label">Locked</span></div></SettingsSection>
    <SettingsSection title="Profanity dictionary" description="Curated backend policy files"><div className="policy-inventory"><div><strong>{dictionary?.words_count ?? '—'}</strong><span>Censored words</span><small>{dictionary?.words_path ?? 'Loading policy'}</small></div><div><strong>{dictionary?.exclusions_count ?? '—'}</strong><span>Exclusions</span><small>{dictionary?.exclusions_path ?? 'Loading policy'}</small></div></div></SettingsSection>
    <SettingsSection title="About" description="Desktop application identity"><div className="about-setting"><strong>Profanity Censor 0.1.0</strong><span>Electron desktop · local processing · Windows</span></div></SettingsSection>
  </div></section>
}
function SettingsSection({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <section className="settings-section"><header><h2>{title}</h2><p>{description}</p></header><div className="settings-content">{children}</div></section> }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}</label> }
function NumberInput({ value, onChange }: { value: number; onChange: (value: number) => void }) { return <div className="number-input"><input type="number" min={0} max={10000} value={value} onChange={(event) => onChange(Number(event.target.value))} /><span>ms</span></div> }
function Segmented<T extends string>({ value, options, onChange }: { value: T; options: Array<[T, string]>; onChange: (value: T) => void }) { return <div className="segmented">{options.map(([option, label]) => <button type="button" className={value === option ? 'selected' : ''} onClick={() => onChange(option)} key={option}>{label}</button>)}</div> }
export default App
