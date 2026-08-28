import { AlertCircle, Check } from 'lucide-react'
import type { Capabilities } from '../types/domain'

type SetupBandProps = {
  capabilities: Capabilities
  installRequired: (components: string[]) => void
  busy: boolean
}

export function SetupBand({ capabilities, installRequired, busy }: SetupBandProps) {
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
          action={
            !(capabilities.ffmpeg && capabilities.ffprobe)
              ? () => installRequired(['ffmpeg'])
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
          action={!capabilities.whisper ? () => installRequired(['python']) : undefined}
        />
        <SetupItem
          label={`Whisper ${capabilities.whisper_model}`}
          ready={capabilities.whisper_model_ready}
          busy={busy}
          action={
            !capabilities.whisper_model_ready && capabilities.whisper
              ? () => installRequired(['whisper_model'])
              : undefined
          }
        />
      </div>
    </section>
  )
}

type SetupItemProps = {
  label: string
  ready: boolean
  busy: boolean
  action?: () => void
}

function SetupItem({ label, ready, busy, action }: SetupItemProps) {
  return (
    <div className="setup-item">
      {ready ? <Check size={17} /> : <AlertCircle size={17} />}
      <span>{label}</span>
      <strong>{ready ? 'Ready' : 'Missing'}</strong>
      {action && <button disabled={busy} onClick={action}>Install</button>}
    </div>
  )
}

