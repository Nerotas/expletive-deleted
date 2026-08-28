import { startTransition, useCallback, useEffect, useState, type ReactNode } from 'react'
import { AlertCircle, ArchiveIcon, BookOpen, Check, CircleStop, FolderOpen, ListVideo, LoaderCircle, MoonIcon, Play, RefreshCw, RotateCcw, Save, Settings as SettingsIcon, ShieldCheck, SunIcon } from 'lucide-react'
import appIconUrl from './assets/profanity-censor-icon.svg'
import './App.css'
import './queue-details.css'
import './dictionary.css'
import './theme.css'

type Page = 'queue' | 'dictionary' | 'settings'
type Theme = 'light' | 'dark'
type LibraryStatus = 'ready' | 'transcribed' | 'finished'
type JobStatus = 'queued' | 'transcribing' | 'transcribed' | 'censoring' | 'verifying' | 'completed' | 'failed' | 'cancelled'
type LibraryItem = { source: string; status: LibraryStatus; transcript: string | null; output: string | null }
type JobError = { code: string; message: string; detail: string | null; retryable: boolean }
type Job = { id: string; source: string; mode: 'report_only' | 'censor'; status: JobStatus; progress_percent: number | null; error: JobError | null }
type JobEvent = { event: string; job_id: string; sequence: number; stage: JobStatus | null; percent: number | null; eta_seconds: number | null; fps: number | null; message: string | null }
type WhisperLibrary = 'faster-whisper' | 'openai-whisper'
type WhisperModel = 'tiny' | 'base' | 'small' | 'medium' | 'large-v3'
type Capabilities = { ready: boolean; ffmpeg: boolean; ffprobe: boolean; whisper: boolean; whisper_library: WhisperLibrary; whisper_model: WhisperModel; whisper_model_ready: boolean; whisper_device: string; video_encoders: string[] }
type DictionaryInfo = { words_path: string; words_count: number; words: string[]; exclusions_path: string; exclusions_count: number; exclusions: string[]; discovered_count: number; discovered: string[]; changed?: boolean }
type ReviewCandidate = { word: string; start: number | null; end: number | null }
type ReviewResult = { source: string; candidates: ReviewCandidate[] }
type Settings = {
  schema_version: number
  directories: { input: string; output: string; archive: string; transcripts: string }
  processing: { mode: 'report_only' | 'censor'; device: 'auto' | 'cpu' | 'cuda' }
  censoring: { stereo_method: 'drop_audio' | 'karaoke'; padding_before_ms: number; padding_after_ms: number }
  audio: { surround_output: 'preserve_5_1' | 'downmix_stereo' }
  video: { mode: 'h264' | 'preserve_source' }
  whisper: { library: WhisperLibrary; model: WhisperModel }
  source: { archive_after_success: boolean; scan_subdirectories: boolean }
  runtime: { ffmpeg_path: string | null; ffprobe_path: string | null; whisper_cache: string | null }
}
type InstallPlan = { plan_id: string }

const desktopApi = () => {
  if (!window.profanityCensor) throw new Error('The Electron preload bridge did not load. Restart the desktop application.')
  return window.profanityCensor
}
const invoke = <T,>(method: string, params?: Record<string, unknown>) => desktopApi().invoke<T>(method, params)
const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path
const formatEta = (seconds: number) => { const total = Math.max(0, Math.round(seconds)); const minutes = Math.floor(total / 60); return minutes ? `${minutes}m ${total % 60}s` : `${total}s` }
const statusLabel = (status: LibraryStatus | JobStatus) => ({ ready: 'Ready', transcribed: 'Transcribed', finished: 'Finished', queued: 'Ready', transcribing: 'Transcribing', censoring: 'Censoring', verifying: 'Verifying', completed: 'Finished', failed: 'Failed', cancelled: 'Cancelled' })[status]

function App() {
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem('profanity-censor-theme') === 'dark' ? 'dark' : 'light')
  const [page, setPage] = useState<Page>('queue')
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [settingsDirty, setSettingsDirty] = useState(false)
  const [library, setLibrary] = useState<LibraryItem[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [jobEvents, setJobEvents] = useState<Record<string, JobEvent>>({})
  const [dictionary, setDictionary] = useState<DictionaryInfo | null>(null)
  const [review, setReview] = useState<ReviewResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [nextSettings, nextLibrary, nextJobs] = await Promise.all([
        invoke<Settings>('settings.get'), invoke<LibraryItem[]>('library.list'), invoke<Job[]>('jobs.list'),
      ])
      startTransition(() => { if (!settingsDirty) setSettings(nextSettings); setLibrary(nextLibrary); setJobs(nextJobs) })
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
  }, [settingsDirty])

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0)
    const timer = window.setInterval(() => void refresh(true), 1500)
    return () => { window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refresh])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    localStorage.setItem('profanity-censor-theme', theme)
  }, [theme])

  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(null); setNotice(null)
    try { await action(); await refresh(true) }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }

  const saveSettings = async () => {
    if (!settings) return
    await run(async () => { const updated = await invoke<Settings>('settings.update', { settings }); setSettings(updated); setSettingsDirty(false); setCapabilities(await invoke<Capabilities>('capabilities.get')); setNotice('Settings saved') })
  }
  const startBatch = async () => {
    const pending = library.filter((item) => item.status !== 'finished')
    await run(async () => { for (const item of pending) await invoke<Job>('jobs.submit', { source: item.source, mode: settings?.processing.mode ?? 'censor' }); setNotice(`${pending.length} ${pending.length === 1 ? 'file' : 'files'} queued`) })
  }
  const cancelActive = async () => {
    const active = jobs.find((job) => !['completed', 'failed', 'cancelled', 'transcribed'].includes(job.status)); if (!active) return
    await run(async () => { await invoke<Job>('jobs.cancel', { job_id: active.id }); setNotice('Cancellation requested') })
  }
  const installRequired = async (components: string[]) => run(async () => {
    const plan = await invoke<InstallPlan>('dependencies.plan', { components })
    await invoke('dependencies.install', { plan_id: plan.plan_id })
    setCapabilities(await invoke<Capabilities>('capabilities.get'))
    setNotice('Installation complete and verified')
  })
  const chooseDirectory = async (key: keyof Settings['directories']) => {
    if (!settings) return
    const selected = await desktopApi().selectDirectory(settings.directories[key])
    if (selected) { setSettings({ ...settings, directories: { ...settings.directories, [key]: selected } }); setSettingsDirty(true) }
  }
  const retryJob = async (job: Job) => run(async () => { await invoke<Job>('jobs.submit', { source: job.source, mode: job.mode }); setNotice(`${fileName(job.source)} queued again`) })
  const updateDictionary = async (target: 'censor' | 'exclude', word: string, action: 'add' | 'remove' = 'add') => run(async () => {
    const nextDictionary = await invoke<DictionaryInfo>(`dictionary.${action}`, { target, word })
    setDictionary(nextDictionary)
    if (review) setReview({ ...review, candidates: review.candidates.filter((candidate) => candidate.word !== word.trim().toLowerCase()) })
    setNotice(action === 'add' ? `Added ${word} to ${target === 'censor' ? 'censored words' : 'exclusions'}` : `Removed ${word}`)
  })
  const openReview = async (source: string) => run(async () => setReview(await invoke<ReviewResult>('reviews.list', { source })))
  const archiveSource = async (source: string) => run(async () => {
    await invoke('library.archive', { source })
    setNotice(`${fileName(source)} moved to Processed`)
  })

  const mergedRows = library.map((item) => ({ item, job: [...jobs].reverse().find((candidate) => candidate.source === item.source) }))
  const activeJob = jobs.find((job) => !['completed', 'failed', 'cancelled', 'transcribed'].includes(job.status))

  return <div className="app-shell">
    <header className="app-header">
      <div className="brand-lockup"><img className="brand-mark" src={appIconUrl} alt="" /><div><strong>Profanity Censor</strong><small>Local media processing</small></div></div>
      <nav className="top-nav" aria-label="Application pages"><button className={page === 'queue' ? 'active' : ''} onClick={() => setPage('queue')}><ListVideo size={17} />Queue</button><button className={page === 'dictionary' ? 'active' : ''} onClick={() => setPage('dictionary')}><BookOpen size={17} />Dictionary</button><button className={page === 'settings' ? 'active' : ''} onClick={() => setPage('settings')}><SettingsIcon size={17} />Settings</button></nav>
      <div className="header-status"><button className="theme-toggle" title={`Switch to ${theme === 'light' ? 'night' : 'light'} mode`} aria-label={`Switch to ${theme === 'light' ? 'night' : 'light'} mode`} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <MoonIcon size={16} /> : <SunIcon size={16} />}</button><div className={`runtime-pill ${capabilities?.ready ? 'ready' : 'attention'}`}>{capabilities?.ready ? <ShieldCheck size={16} /> : <AlertCircle size={16} />}{capabilities?.ready ? 'System ready' : 'Setup required'}</div></div>
    </header>
    <main>
      {error && <div className="alert error"><AlertCircle size={18} /><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}
      {notice && <div className="alert success"><Check size={18} /><span>{notice}</span><button onClick={() => setNotice(null)}>Dismiss</button></div>}
      {!loading && capabilities && !capabilities.ready && <section className="setup-band"><div><span className="eyebrow">Required component</span><h2>Finish local setup</h2><p>Processing stays on this computer. Install missing components here, then the app verifies them automatically.</p></div><div className="setup-items"><SetupItem label="FFmpeg + FFprobe" ready={capabilities.ffmpeg && capabilities.ffprobe} action={!(capabilities.ffmpeg && capabilities.ffprobe) ? () => installRequired(['ffmpeg']) : undefined} /><SetupItem label={capabilities.whisper_library === 'openai-whisper' ? 'OpenAI Whisper' : 'faster-whisper'} ready={capabilities.whisper} action={!capabilities.whisper ? () => installRequired(['python']) : undefined} /><SetupItem label={`Whisper ${capabilities.whisper_model}`} ready={capabilities.whisper_model_ready} action={!capabilities.whisper_model_ready && capabilities.whisper ? () => installRequired(['whisper_model']) : undefined} /></div></section>}
      {page === 'queue' ? <section className="page queue-page">
        <PageHeading title="Queue" subtitle={`${library.length} supported ${library.length === 1 ? 'file' : 'files'} in Ready`}><button className="icon-button" title="Refresh queue" onClick={() => void refresh()}><RefreshCw size={18} /></button>{activeJob && <button className="button danger" onClick={cancelActive}><CircleStop size={17} />Cancel</button>}<button className="button primary" disabled={busy || !capabilities?.ready || library.every((item) => item.status === 'finished')} onClick={startBatch}><Play size={17} />Start batch</button></PageHeading>
        <div className="queue-summary"><Metric label="Ready" value={mergedRows.filter(({ item, job }) => !job && item.status === 'ready').length} tone="neutral" /><Metric label="Active" value={activeJob ? 1 : 0} tone="active" /><Metric label="Transcribed" value={mergedRows.filter(({ item, job }) => (job?.status ?? item.status) === 'transcribed').length} tone="warning" /><Metric label="Finished" value={mergedRows.filter(({ item, job }) => ['finished', 'completed'].includes(job?.status ?? item.status)).length} tone="success" /></div>
        <div className="table-frame"><table><thead><tr><th>File</th><th>Status</th><th>Progress</th><th>Details</th></tr></thead><tbody>{mergedRows.map(({ item, job }) => { const status = job?.status ?? item.status; const percent = job?.progress_percent; const event = job ? jobEvents[job.id] : undefined; const detail = event?.fps ? `${Math.round(event.fps)} FPS${event.eta_seconds != null ? ` · ${formatEta(event.eta_seconds)} left` : ''}` : event?.eta_seconds != null ? `${formatEta(event.eta_seconds)} left` : job?.error?.detail ?? (status === 'transcribed' ? 'Report available' : ['completed', 'finished'].includes(status) ? 'Output verified' : activeJob?.id === job?.id ? 'Processing locally' : 'Waiting'); const canArchive = item.status === 'transcribed' || item.status === 'finished'; return <tr key={item.source}><td><div className="file-cell"><span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span><div><strong>{fileName(item.source)}</strong><small>{item.source}</small></div></div></td><td><StatusBadge status={status} /></td><td>{percent != null ? <div className="progress-wrap"><div className="progress-track"><span style={{ width: `${percent}%` }} /></div><span>{Math.round(percent)}%</span></div> : <span className="muted">—</span>}</td><td className="details-cell"><span>{detail}</span>{item.transcript && <button onClick={() => void openReview(item.source)}>Review words</button>}{canArchive && <button disabled={busy || Boolean(activeJob)} onClick={() => void archiveSource(item.source)}><ArchiveIcon size={13} />Archive source</button>}{job?.status === 'failed' && job.error?.retryable && <button onClick={() => retryJob(job)}>Retry</button>}</td></tr> })}{!loading && mergedRows.length === 0 && <tr><td colSpan={4}><div className="empty-state"><FolderOpen size={28} /><strong>No media in Ready</strong><span>Add a supported audio or video file to the configured input folder.</span></div></td></tr>}</tbody></table>{loading && <div className="loading-row"><LoaderCircle className="spin" size={20} />Reading local library</div>}</div>
        <div className="path-bar"><FolderOpen size={16} /><span>{settings?.directories.input}</span><button onClick={() => setPage('settings')}>Change folder</button></div>
      </section> : page === 'dictionary' ? <DictionaryPage dictionary={dictionary} busy={busy} updateDictionary={updateDictionary} /> : settings ? <SettingsPage settings={settings} setSettings={(nextSettings) => { setSettings(nextSettings); setSettingsDirty(true) }} chooseDirectory={chooseDirectory} save={saveSettings} busy={busy} capabilities={capabilities} /> : <div className="loading-row"><LoaderCircle className="spin" size={20} />Loading settings</div>}
    </main>
    {review && <ReviewDialog review={review} busy={busy} onClose={() => setReview(null)} onClassify={(word, target) => void updateDictionary(target, word)} />}
  </div>
}

function PageHeading({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <div className="page-heading"><div><span className="eyebrow">Workspace</span><h1>{title}</h1><p>{subtitle}</p></div><div className="heading-actions">{children}</div></div> }
function SetupItem({ label, ready, action }: { label: string; ready: boolean; action?: () => void }) { return <div className="setup-item">{ready ? <Check size={17} /> : <AlertCircle size={17} />}<span>{label}</span><strong>{ready ? 'Ready' : 'Missing'}</strong>{action && <button onClick={action}>Install</button>}</div> }
function Metric({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div> }
function StatusBadge({ status }: { status: LibraryStatus | JobStatus }) { return <span className={`status-badge status-${status}`}>{['transcribing', 'censoring', 'verifying'].includes(status) && <LoaderCircle className="spin" size={13} />}{statusLabel(status)}</span> }

function SettingsPage({ settings, setSettings, chooseDirectory, save, busy, capabilities }: { settings: Settings; setSettings: (value: Settings) => void; chooseDirectory: (key: keyof Settings['directories']) => void; save: () => void; busy: boolean; capabilities: Capabilities | null }) {
  const setGroup = <K extends keyof Settings>(group: K, value: Settings[K]) => setSettings({ ...settings, [group]: value })
  return <section className="page settings-page"><PageHeading title="Settings" subtitle="Persistent preferences for local processing"><button className="button secondary" onClick={() => window.location.reload()}><RotateCcw size={17} />Discard</button><button className="button primary" disabled={busy} onClick={save}><Save size={17} />Save changes</button></PageHeading><div className="settings-layout">
    <SettingsSection title="Directories" description="User-owned working folders">{(Object.keys(settings.directories) as Array<keyof Settings['directories']>).map((key) => <label className="path-field" key={key}><span>{({ input: 'Ready / Input', output: 'Finished / Output', archive: 'Processed / Archive', transcripts: 'Transcripts' })[key]}</span><div><input value={settings.directories[key]} onChange={(event) => setGroup('directories', { ...settings.directories, [key]: event.target.value })} /><button className="icon-button" title={`Choose ${key} directory`} onClick={() => chooseDirectory(key)}><FolderOpen size={17} /></button></div></label>)}</SettingsSection>
    <SettingsSection title="Processing" description="Choose the workflow and compute device"><Field label="Mode"><Segmented value={settings.processing.mode} options={[['report_only', 'Report only'], ['censor', 'Censor media']]} onChange={(mode) => setGroup('processing', { ...settings.processing, mode })} /></Field><Field label="Device"><select value={settings.processing.device} onChange={(event) => setGroup('processing', { ...settings.processing, device: event.target.value as Settings['processing']['device'] })}><option value="auto">Automatic ({capabilities?.whisper_device ?? 'detecting'})</option><option value="cpu">CPU</option><option value="cuda">CUDA</option></select></Field></SettingsSection>
    <SettingsSection title="Censoring" description="Audio treatment and interval timing"><Field label="Stereo method"><Segmented value={settings.censoring.stereo_method} options={[['drop_audio', 'Drop audio'], ['karaoke', 'Karaoke']]} onChange={(stereo_method) => setGroup('censoring', { ...settings.censoring, stereo_method })} /></Field><div className="field-pair"><Field label="Before word"><NumberInput value={settings.censoring.padding_before_ms} onChange={(padding_before_ms) => setGroup('censoring', { ...settings.censoring, padding_before_ms })} /></Field><Field label="After word"><NumberInput value={settings.censoring.padding_after_ms} onChange={(padding_after_ms) => setGroup('censoring', { ...settings.censoring, padding_after_ms })} /></Field></div></SettingsSection>
    <SettingsSection title="Output" description="Audio layout, video handling, and source safety"><Field label="Surround audio"><Segmented value={settings.audio.surround_output} options={[['preserve_5_1', 'Preserve 5.1'], ['downmix_stereo', 'Downmix to stereo']]} onChange={(surround_output) => setGroup('audio', { surround_output })} /></Field><Field label="Video"><Segmented value={settings.video.mode} options={[['h264', 'H.264'], ['preserve_source', 'Preserve source']]} onChange={(mode) => setGroup('video', { mode })} /></Field><label className="toggle-row"><div><strong>Scan subdirectories</strong><span>Include supported media inside folders under Ready.</span></div><input type="checkbox" checked={settings.source.scan_subdirectories} onChange={(event) => setGroup('source', { ...settings.source, scan_subdirectories: event.target.checked })} /></label><label className="toggle-row"><div><strong>Archive original after success</strong><span>Off by default. Never moves source files after failure or cancellation.</span></div><input type="checkbox" checked={settings.source.archive_after_success} onChange={(event) => setGroup('source', { ...settings.source, archive_after_success: event.target.checked })} /></label></SettingsSection>
    <SettingsSection title="Whisper" description="Choose the accuracy and speed profile for transcription"><Field label="Library"><select value={settings.whisper.library} onChange={(event) => setGroup('whisper', { ...settings.whisper, library: event.target.value as WhisperLibrary })}><option value="faster-whisper">faster-whisper — recommended, much faster</option><option value="openai-whisper">OpenAI Whisper — accuracy-first, much slower</option></select></Field><Field label="Model"><select value={settings.whisper.model} onChange={(event) => setGroup('whisper', { ...settings.whisper, model: event.target.value as WhisperModel })}><option value="large-v3">large-v3 — recommended, highest accuracy</option><option value="medium">medium — faster, lower accuracy</option><option value="small">small — substantially lower accuracy</option><option value="base">base — major accuracy tradeoff</option><option value="tiny">tiny — fastest, lowest accuracy</option></select></Field><div className={`whisper-notice ${settings.whisper.model === 'large-v3' ? 'recommended' : 'warning'}`}><AlertCircle size={17} /><div><strong>{settings.whisper.model === 'large-v3' ? 'Recommended for reliable censoring' : `${settings.whisper.model} trades accuracy for speed`}</strong><span>{settings.whisper.model === 'large-v3' ? 'large-v3 remains the default because it produces the most consistent word detection and timestamps.' : 'Quality and timestamp accuracy drop noticeably with smaller models. Review transcripts and discovered words carefully.'}</span></div></div><small className="whisper-library-note">Changing the library or model requires its local component download. Existing transcripts from another profile will be regenerated.</small></SettingsSection>
    <SettingsSection title="About" description="Desktop application identity"><div className="about-setting"><strong>Profanity Censor 0.1.0</strong><span>Electron desktop · local processing · Windows</span></div></SettingsSection>
  </div></section>
}
function DictionaryPage({ dictionary, busy, updateDictionary }: { dictionary: DictionaryInfo | null; busy: boolean; updateDictionary: (target: 'censor' | 'exclude', word: string, action?: 'add' | 'remove') => Promise<void> }) { return <section className="page dictionary-page"><PageHeading title="Dictionary" subtitle="Review discoveries and manage the policy used for future jobs"><span className="dictionary-total">{(dictionary?.words_count ?? 0) + (dictionary?.exclusions_count ?? 0)} classified</span></PageHeading><div className="dictionary-workspace"><DictionaryEditor dictionary={dictionary} busy={busy} updateDictionary={updateDictionary} /></div></section> }
function DictionaryEditor({ dictionary, busy, updateDictionary }: { dictionary: DictionaryInfo | null; busy: boolean; updateDictionary: (target: 'censor' | 'exclude', word: string, action?: 'add' | 'remove') => Promise<void> }) { const [word, setWord] = useState(''); const [target, setTarget] = useState<'censor' | 'exclude'>('censor'); const add = async () => { if (!word.trim()) return; await updateDictionary(target, word); setWord('') }; return <><div className="dictionary-add"><input aria-label="Word or phrase" value={word} placeholder="Word or phrase" onChange={(event) => setWord(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void add() }} /><select value={target} onChange={(event) => setTarget(event.target.value as 'censor' | 'exclude')}><option value="censor">Censor</option><option value="exclude">Ignore</option></select><button className="button primary" disabled={busy || !word.trim()} onClick={() => void add()}>Add</button></div><div className="policy-lists"><DiscoveredList words={dictionary?.discovered ?? []} count={dictionary?.discovered_count} busy={busy} onClassify={(item, destination) => updateDictionary(destination, item)} /><PolicyList title={`Censored words (${dictionary?.words_count ?? '—'})`} words={dictionary?.words ?? []} busy={busy} onRemove={(item) => updateDictionary('censor', item, 'remove')} /><PolicyList title={`Exclusions (${dictionary?.exclusions_count ?? '—'})`} words={dictionary?.exclusions ?? []} busy={busy} onRemove={(item) => updateDictionary('exclude', item, 'remove')} /></div></> }
function DiscoveredList({ words, count, busy, onClassify }: { words: string[]; count?: number; busy: boolean; onClassify: (word: string, target: 'censor' | 'exclude') => Promise<void> }) { return <div className="discovered-list"><div><strong>{`Discovered words (${count ?? '—'})`}</strong><small>Potential profanity found in saved transcripts but not yet classified.</small></div>{words.length ? <div className="discovered-words">{words.map((word) => <div key={word}><span>{word}</span><button disabled={busy} onClick={() => void onClassify(word, 'censor')}>Censor</button><button disabled={busy} onClick={() => void onClassify(word, 'exclude')}>Ignore</button></div>)}</div> : <small className="empty-discovered">No unclassified words discovered yet.</small>}</div> }
function PolicyList({ title, words, busy, onRemove }: { title: string; words: string[]; busy: boolean; onRemove: (word: string) => Promise<void> }) { return <div className="policy-list"><strong>{title}</strong><div>{words.length ? words.map((word) => <span key={word}>{word}<button disabled={busy} aria-label={`Remove ${word}`} onClick={() => void onRemove(word)}>×</button></span>) : <small>Loading policy…</small>}</div></div> }
function ReviewDialog({ review, busy, onClose, onClassify }: { review: ReviewResult; busy: boolean; onClose: () => void; onClassify: (word: string, target: 'censor' | 'exclude') => void }) { return <div className="modal-backdrop"><section className="modal review-dialog" role="dialog" aria-modal="true" aria-labelledby="review-title"><span className="eyebrow">Potential profanity</span><h2 id="review-title">Review discovered words</h2><p>{fileName(review.source)} · These vendor-list matches are not in your current policy.</p>{review.candidates.length ? <div className="review-list">{review.candidates.map((candidate, index) => <div key={`${candidate.word}-${candidate.start}-${index}`}><strong>{candidate.word}</strong><span>{candidate.start != null ? `${formatEta(candidate.start)} in` : 'Timestamp unavailable'}</span><button disabled={busy} onClick={() => onClassify(candidate.word, 'censor')}>Censor</button><button disabled={busy} onClick={() => onClassify(candidate.word, 'exclude')}>Ignore</button></div>)}</div> : <div className="empty-review">No unclassified potential profanity was found.</div>}<div className="modal-actions"><button className="button secondary" onClick={onClose}>Close</button></div></section></div> }
function SettingsSection({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <section className="settings-section"><header><h2>{title}</h2><p>{description}</p></header><div className="settings-content">{children}</div></section> }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}</label> }
function NumberInput({ value, onChange }: { value: number; onChange: (value: number) => void }) { return <div className="number-input"><input type="number" min={0} max={10000} value={value} onChange={(event) => onChange(Number(event.target.value))} /><span>ms</span></div> }
function Segmented<T extends string>({ value, options, onChange }: { value: T; options: Array<[T, string]>; onChange: (value: T) => void }) { return <div className="segmented">{options.map(([option, label]) => <button type="button" className={value === option ? 'selected' : ''} onClick={() => onChange(option)} key={option}>{label}</button>)}</div> }
export default App
