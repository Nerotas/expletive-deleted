import { RefreshCw } from 'lucide-react'
import type { Capabilities } from '../../types/domain'
import { ComponentRow } from './ComponentRow'
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
  const pythonReady = Boolean(capabilities?.whisper)
  const mediaReady = Boolean(capabilities?.ffmpeg && capabilities?.ffprobe)
  const youtubeReady = Boolean(capabilities?.ytdlp && capabilities?.js_runtime)
  const modelReady = Boolean(capabilities?.speech_model === 'ready' || capabilities?.whisper_model_ready)
  const youtubeDetail = youtubeReady
    ? 'yt-dlp and its JavaScript runtime are verified.'
    : [capabilities?.ytdlp_detail, capabilities?.js_runtime_detail].filter(Boolean).join(' ')
      || 'yt-dlp and Deno are needed to import YouTube videos.'
  const pendingComponents = [
    ...(!pythonReady ? ['python'] : []),
    ...(!mediaReady ? ['ffmpeg'] : []),
    ...(!youtubeReady ? ['ytdlp', 'js_runtime'] : []),
    ...(!modelReady ? ['whisper_model'] : []),
  ]

  return <>
    <OnboardingStepHeading title="Prepare this computer" subtitle="Choose which local components to set up. Downloads happen only after you approve them, and your media stays on this computer." />
    <div className="component-list">
      <ComponentRow title="Transcription packages" detail={pythonReady ? 'Pinned faster-whisper packages are verified.' : 'Install the pinned local transcription packages into the private Python runtime.'} ready={pythonReady} checking={checking} busy={busy} />
      <ComponentRow title="FFmpeg and FFprobe" detail={mediaReady ? `Verified${capabilities?.ffmpeg_version ? ` (${capabilities.ffmpeg_version})` : ''}.` : 'Needed to inspect, remux, and censor local media.'} ready={mediaReady} checking={checking} busy={busy} />
      <ComponentRow title="YouTube tools" detail={youtubeDetail} ready={youtubeReady} checking={checking} busy={busy} />
      <ComponentRow title="Whisper large-v3 model" detail="Download the supported speech model when you are ready. It stays on this computer." ready={modelReady} checking={checking} busy={busy} optional />
    </div>
    {pendingComponents.length ? <div className="onboarding-get-all">
      <div><strong>Set up components</strong><span>You can continue with warnings and return here later to retry anything that is missing.</span></div>
      <button className="button primary" disabled={busy} onClick={() => onReviewInstall(pendingComponents)}>{modelReady ? 'Set up missing components' : 'Review setup'}</button>
    </div> : null}
    <button className="button secondary check-components" disabled={busy} onClick={onCheckAgain}>
      <RefreshCw className={checking ? 'spin' : undefined} size={16} />Check again
    </button>
  </>
}
