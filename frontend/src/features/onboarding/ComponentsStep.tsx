import { Check, RefreshCw } from 'lucide-react'
import type { Capabilities } from '../../types/domain'
import { OnboardingStepHeading } from './OnboardingStepHeading'

type ComponentsStepProps = {
  capabilities: Capabilities | null
  checking: boolean
  busy: boolean
  onReviewInstall: (components: string[]) => void
  onLocateExisting: (component: 'ffmpeg' | 'whisper_model' | 'ytdlp') => void
  onCheckAgain: () => void
}

export function ComponentsStep({ capabilities, checking, busy, onReviewInstall, onCheckAgain }: ComponentsStepProps) {
  const modelReady = Boolean(capabilities?.speech_model === 'ready' || capabilities?.whisper_model_ready)
  const bundledRuntimeInvalid = capabilities?.app_runtime_source === 'bundled' && capabilities.app_runtime === 'invalid'
  const developmentRuntimeMissing = capabilities?.app_runtime_source === 'development' && capabilities.app_runtime !== 'ready'

  return <>
    <OnboardingStepHeading title="Prepare this computer" subtitle="The app checks its included tools automatically. You choose whether to download the speech model, and your media stays on this computer." />
    <div className="component-list">
      {bundledRuntimeInvalid ? <ComponentRow title="Expletive Deleted components" detail={capabilities?.app_runtime_detail ?? 'An included application component needs repair.'} ready={false} checking={checking} busy={busy} /> : null}
      {developmentRuntimeMissing ? <ComponentRow title="Development runtime components" detail={capabilities?.app_runtime_detail ?? 'A development runtime component needs attention.'} ready={false} checking={checking} busy={busy} /> : null}
      <ComponentRow title="Whisper large-v3 model" detail="Download the supported speech model when you are ready. It stays on this computer." ready={modelReady} checking={checking} busy={busy} optional />
    </div>
    {!bundledRuntimeInvalid && !modelReady ? <div className="onboarding-get-all">
      <div><strong>Choose speech recognition</strong><span>Download the supported model only when you are ready. It stays on this computer.</span></div>
      <button className="button primary" disabled={busy} onClick={() => onReviewInstall(['whisper_model'])}>Download large-v3 model</button>
    </div> : null}
    <button className="button secondary check-components" disabled={busy} onClick={onCheckAgain}>
      <RefreshCw className={checking ? 'spin' : undefined} size={16} />Check again
    </button>
  </>
}

function ComponentRow({ title, detail, ready, checking, busy, onLocate, onGet, optional = false }: {
  title: string
  detail: string
  ready: boolean
  checking: boolean
  busy: boolean
  onLocate?: () => void
  onGet?: () => void
  optional?: boolean
}) {
  const state = checking ? 'Checking' : ready ? 'Verified' : optional ? 'Not downloaded' : 'Needs attention'
  return <article className="component-row">
    <span className={ready ? 'ready' : optional ? 'informational' : undefined}>{ready ? <Check size={16} /> : optional ? 'i' : '!'}</span>
    <div><strong>{title}</strong><small>{detail}</small></div>
    <b>{state}</b>
    {!ready && <div className="component-actions">
      {onLocate && <button className="button secondary" disabled={busy} onClick={onLocate}>Locate existing</button>}
      {onGet && <button className="button primary" disabled={busy} onClick={onGet}>Download model</button>}
    </div>}
  </article>
}
