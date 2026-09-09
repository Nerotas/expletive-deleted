import { AlertCircle, Check, RefreshCw } from 'lucide-react'
import type { Capabilities } from '../types/domain'

type SetupBandProps = {
  capabilities: Capabilities
  reviewInstall: (components: string[]) => void
  checkAgain: () => void
  busy: boolean
}

export function SetupBand({ capabilities, reviewInstall, checkAgain, busy }: SetupBandProps) {
  const bundledRuntime = capabilities.app_runtime_source === 'bundled'
  const modelReady = capabilities.speech_model === 'ready' || capabilities.whisper_model_ready
  const bundledRuntimeInvalid = bundledRuntime && capabilities.app_runtime === 'invalid'

  return (
    <section className="setup-band">
      <div>
        <span className="eyebrow">System check</span>
        <h2>{bundledRuntime ? 'Local processing status' : 'Local components'}</h2>
        <p>{bundledRuntime
          ? 'The app checks its included tools automatically. The speech model is a separate choice that stays on this computer.'
          : 'The app checks its processing components automatically. The speech model is a separate choice that stays on this computer.'}
        </p>
      </div>
      <div className="setup-items">
        {bundledRuntimeInvalid ? <SetupItem label="Expletive Deleted components" detail={capabilities.app_runtime_detail} ready={false} busy={busy} /> : null}
        <SetupItem label={`Whisper ${capabilities.whisper_model}`} detail="Download the supported speech model when you are ready. It stays on this computer." ready={modelReady} busy={busy} optional />
      </div>
      <div className="setup-band-controls">
        {!bundledRuntimeInvalid && !modelReady ? <button className="setup-get-all" disabled={busy} onClick={() => reviewInstall(['whisper_model'])}>Download large-v3 model</button> : null}
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
  optional?: boolean
}

function SetupItem({ label, detail, ready, busy, action, actionLabel = 'Get Components', locate, optional = false }: SetupItemProps) {
  const resolvedActionLabel = optional ? 'Download model' : actionLabel
  return <div className="setup-item">
    {ready ? <Check size={17} /> : optional ? <span className="setup-item-info">i</span> : <AlertCircle size={17} />}
    <span>{label}{detail ? <small>{detail}</small> : null}</span>
    <strong>{ready ? 'Ready' : optional ? 'Not downloaded' : 'Needs attention'}</strong>
    {!ready && (locate || action) && <div className="setup-item-actions">
      {locate && <button className="secondary" disabled={busy} onClick={locate}>Locate existing</button>}
      {action && <button disabled={busy} onClick={action}>{resolvedActionLabel}</button>}
    </div>}
  </div>
}
