import { AlertCircle, Check, RefreshCw } from 'lucide-react'
import type { Capabilities } from '../types/domain'

type SetupBandProps = {
  capabilities: Capabilities
  reviewInstall: (components: string[]) => void
  locateExisting: (component: 'ffmpeg' | 'whisper_model') => void
  checkAgain: () => void
  busy: boolean
}

export function SetupBand({ capabilities, reviewInstall, locateExisting, checkAgain, busy }: SetupBandProps) {
  return (
    <section className="setup-band">
      <div>
        <span className="eyebrow">Required component</span>
        <h2>Finish local setup</h2>
        <p>
          Processing stays on this computer. Install missing components here, then the app
          verifies them automatically.
        </p>
      </div>
      <div className="setup-items">
        <SetupItem
          label="FFmpeg + FFprobe"
          ready={capabilities.ffmpeg && capabilities.ffprobe}
          busy={busy}
          locate={() => locateExisting('ffmpeg')}
          action={
            !(capabilities.ffmpeg && capabilities.ffprobe)
              ? () => reviewInstall(['ffmpeg'])
              : undefined
          }
        />
        <SetupItem
          label={
            capabilities.whisper_library === 'openai-whisper'
              ? 'OpenAI Whisper'
              : 'faster-whisper'
          }
          ready={capabilities.whisper}
          busy={busy}
          action={!capabilities.whisper ? () => reviewInstall(['python']) : undefined}
        />
        <SetupItem
          label={`Whisper ${capabilities.whisper_model}`}
          ready={capabilities.whisper_model_ready}
          busy={busy}
          locate={() => locateExisting('whisper_model')}
          action={
            !capabilities.whisper_model_ready
              ? () => reviewInstall(['whisper_model'])
              : undefined
          }
        />
      </div>
      <button className="setup-check" disabled={busy} onClick={checkAgain}>
        <RefreshCw className={busy ? 'spin' : undefined} size={15} /> Check again
      </button>
    </section>
  )
}

type SetupItemProps = {
  label: string
  ready: boolean
  busy: boolean
  action?: () => void
  locate?: () => void
}

function SetupItem({ label, ready, busy, action, locate }: SetupItemProps) {
  return (
    <div className="setup-item">
      {ready ? <Check size={17} /> : <AlertCircle size={17} />}
      <span>{label}</span>
      <strong>{ready ? 'Ready' : 'Missing'}</strong>
      {!ready && (locate || action) && (
        <div className="setup-item-actions">
          {locate && <button className="secondary" disabled={busy} onClick={locate}>Locate existing</button>}
          {action && <button disabled={busy} onClick={action}>Get</button>}
        </div>
      )}
    </div>
  )
}
