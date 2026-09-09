import { AlertCircle, Check, RefreshCw } from 'lucide-react'
import type { Capabilities } from '../types/domain'

type SetupBandProps = {
  capabilities: Capabilities
  reviewInstall: (components: string[]) => void
  locateExisting: (component: 'ffmpeg' | 'whisper_model' | 'ytdlp') => void
  checkAgain: () => void
  busy: boolean
}

export function SetupBand({ capabilities, reviewInstall, locateExisting, checkAgain, busy }: SetupBandProps) {
  const bundledRuntime = capabilities.app_runtime_source === 'bundled'
  const appRuntimeReady = capabilities.app_runtime === 'ready'
  const modelReady = capabilities.speech_model === 'ready' || capabilities.whisper_model_ready
  const processingReady = capabilities.processing_ready ?? capabilities.ready

  return (
    <section className="setup-band">
      <div>
        <span className="eyebrow">System check</span>
        <h2>{bundledRuntime ? 'Local processing status' : 'Local components'}</h2>
        <p>{bundledRuntime
          ? 'The app checks its included tools automatically. The speech model is a separate choice that stays on this computer.'
          : 'Processing stays on this computer. Install missing components here, then the app verifies them automatically.'}
        </p>
      </div>
      <div className="setup-items">
        {bundledRuntime ? <SetupItem label="Expletive Deleted components" detail={capabilities.app_runtime_detail} ready={appRuntimeReady} busy={busy} /> : <>
          <SetupItem label="FFmpeg + FFprobe" ready={capabilities.ffmpeg && capabilities.ffprobe} busy={busy} locate={() => locateExisting('ffmpeg')} action={!(capabilities.ffmpeg && capabilities.ffprobe) ? () => reviewInstall(['ffmpeg']) : undefined} />
          <SetupItem label="faster-whisper" ready={capabilities.whisper} busy={busy} action={!capabilities.whisper ? () => reviewInstall(['python']) : undefined} />
        </>}
        <SetupItem label={`Whisper ${capabilities.whisper_model}`} ready={modelReady} busy={busy} actionLabel="Download model" locate={() => locateExisting('whisper_model')} action={!modelReady ? () => reviewInstall(['whisper_model']) : undefined} />
        <SetupItem label="yt-dlp (YouTube downloads, optional)" ready={Boolean(capabilities.ytdlp)} busy={busy} actionLabel="Get yt-dlp" locate={() => locateExisting('ytdlp')} action={!capabilities.ytdlp ? () => reviewInstall(['ytdlp']) : undefined} />
      </div>
      <div className="setup-band-controls">
        {bundledRuntime && !modelReady && appRuntimeReady ? <button className="setup-get-all" disabled={busy} onClick={() => reviewInstall(['whisper_model'])}>Download large-v3 model</button> : null}
        {!bundledRuntime && !processingReady ? <button className="setup-get-all" disabled={busy} onClick={() => reviewInstall(['ffmpeg', 'python', 'whisper_model'])}>Get required components</button> : null}
        <button className="setup-check" disabled={busy} onClick={checkAgain}><RefreshCw className={busy ? 'spin' : undefined} size={15} /> Check again</button>
      </div>
    </section>
  )
}

type SetupItemProps = {
  label: string
  detail?: string
  ready: boolean
  busy: boolean
  action?: () => void
  actionLabel?: string
  locate?: () => void
}

function SetupItem({ label, detail, ready, busy, action, actionLabel = 'Get Components', locate }: SetupItemProps) {
  return <div className="setup-item">
    {ready ? <Check size={17} /> : <AlertCircle size={17} />}
    <span>{label}{detail ? <small>{detail}</small> : null}</span>
    <strong>{ready ? 'Ready' : 'Needs attention'}</strong>
    {!ready && (locate || action) && <div className="setup-item-actions">
      {locate && <button className="secondary" disabled={busy} onClick={locate}>Locate existing</button>}
      {action && <button disabled={busy} onClick={action}>{actionLabel}</button>}
    </div>}
  </div>
}
