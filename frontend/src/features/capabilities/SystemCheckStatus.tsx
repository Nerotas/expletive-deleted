import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import type { SystemCheck, SystemCheckStage } from '../../types/domain'

type Props = { checking: boolean; state?: SystemCheck | null; error: string | null; onRetry: () => void }

const labels: Record<SystemCheckStage, string> = {
  starting: 'Starting verification', waiting_previous_check: 'Finishing the earlier check before verifying updated settings',
  media_tools: 'Locating media tools', ffmpeg: 'Checking FFmpeg', ffprobe: 'Checking FFprobe',
  python_packages: 'Verifying processing packages', speech_model: 'Verifying the speech model',
  ytdlp: 'Checking YouTube download tools', js_runtime: 'Checking the YouTube JavaScript runtime',
  device: 'Checking processing device support', encoders: 'Checking video output support',
}

export function SystemCheckStatus({ checking, state, error, onRetry }: Props) {
  if (!checking && !error && !state) return null
  return <section className="system-check-status" aria-label="System check">
    {checking ? <CheckingProgress key={state?.check_id} state={state} /> : error ? <>
      <p role="alert">{error}</p>
      <button className="button secondary" type="button" onClick={onRetry}><RefreshCw size={16} />{state?.status === 'failed' ? 'Retry system check' : 'Reconnect to system check'}</button>
    </> : <p>System verification completed in {((state?.elapsed_ms ?? 0) / 1000).toFixed(1)}s.</p>}
    {state && Object.keys(state.timings).length > 0 && <details>
      <summary>Component timings</summary>
      <ul>{Object.entries(state.timings).map(([stage, ms]) => <li key={stage}>{labels[stage as SystemCheckStage]}: {(ms! / 1000).toFixed(2)}s</li>)}</ul>
    </details>}
  </section>
}

function CheckingProgress({ state }: { state?: SystemCheck | null }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [acknowledged, setAcknowledged] = useState(false)
  useEffect(() => {
    const started = performance.now()
    const timer = setInterval(() => setElapsedSeconds(Math.floor((performance.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [])
  const elapsed = state ? Math.floor(state.elapsed_ms / 1000) : elapsedSeconds
  const slow = elapsed >= 60 && !acknowledged

  return <>
    <p role="status">{slow ? 'Verification is taking longer than expected. Readiness remains unverified.' : state ? labels[state.stage] : 'Verifying local processing packages, media tools, and the speech model.'}</p>
    <small>{elapsed}s elapsed{state ? ` · ${labels[state.stage]} (${(state.stage_elapsed_ms / 1000).toFixed(1)}s)` : ''}. No downloads or installations.</small>
    {slow && <button className="button secondary" type="button" onClick={() => setAcknowledged(true)}>Continue waiting</button>}
  </>
}
