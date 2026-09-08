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

export function ComponentsStep({ capabilities, checking, busy, onReviewInstall, onLocateExisting, onCheckAgain }: ComponentsStepProps) {
  const requiredComponents = [
    !(capabilities?.ffmpeg && capabilities?.ffprobe) && 'ffmpeg',
    !capabilities?.whisper && 'python',
    !(capabilities?.whisper_model_ready && capabilities.whisper_model === 'large-v3') && 'whisper_model',
  ].filter((component): component is string => Boolean(component))

  return <>
    <OnboardingStepHeading title="Prepare this computer" subtitle="Each part is checked separately. The app explains what it needs before retrieving anything, and you stay in control." />
    <div className="component-list">
      <ComponentRow title="FFmpeg and FFprobe" detail="Reads media and creates the censored copy." ready={Boolean(capabilities?.ffmpeg && capabilities?.ffprobe)} checking={checking} busy={busy} onLocate={() => onLocateExisting('ffmpeg')} onGet={() => onReviewInstall(['ffmpeg'])} />
      <ComponentRow title="Speech recognition" detail="faster-whisper turns spoken language into a private, local transcript." ready={Boolean(capabilities?.whisper)} checking={checking} busy={busy} onGet={() => onReviewInstall(['python'])} />
      <ComponentRow title="Whisper large-v3 model" detail="The supported model for recognizing words and their timing. It is a separate download." ready={Boolean(capabilities?.whisper_model_ready && capabilities.whisper_model === 'large-v3')} checking={checking} busy={busy} onLocate={() => onLocateExisting('whisper_model')} onGet={capabilities?.whisper ? () => onReviewInstall(['whisper_model']) : undefined} />
      <ComponentRow title="yt-dlp for YouTube downloads (optional)" detail="Needed only when you choose to download an individual YouTube video. Local files do not need it." ready={Boolean(capabilities?.ytdlp)} checking={checking} busy={busy} onLocate={() => onLocateExisting('ytdlp')} onGet={() => onReviewInstall(['ytdlp'])} optional />
    </div>
    {requiredComponents.length > 1 && <div className="onboarding-get-all">
      <div><strong>Set up everything required</strong><span>Review one combined plan for the missing processing components before anything is retrieved.</span></div>
      <button className="button primary" disabled={busy} onClick={() => onReviewInstall(requiredComponents)}>Get required components</button>
    </div>}
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
  const state = checking ? 'Checking' : ready ? 'Verified' : optional ? 'Optional' : 'Needs attention'
  return <article className="component-row">
    <span className={ready ? 'ready' : undefined}>{ready ? <Check size={16} /> : '!'}</span>
    <div><strong>{title}</strong><small>{detail}</small></div>
    <b>{state}</b>
    {!ready && <div className="component-actions">
      {onLocate && <button className="button secondary" disabled={busy} onClick={onLocate}>Locate existing</button>}
      {onGet && <button className="button primary" disabled={busy} onClick={onGet}>Get Components</button>}
    </div>}
  </article>
}
