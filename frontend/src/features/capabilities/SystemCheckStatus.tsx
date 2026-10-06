import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

type Props = { checking: boolean; error: string | null; onRetry: () => void }

export function SystemCheckStatus({ checking, error, onRetry }: Props) {
  if (!checking && !error) return null
  return <section className="system-check-status" aria-label="System check">
    {checking ? <CheckingProgress /> : <>
      <p role="alert">{error}</p>
      <button className="button secondary" type="button" onClick={onRetry}><RefreshCw size={16} />Retry system check</button>
    </>}
  </section>
}

function CheckingProgress() {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  useEffect(() => {
    const started = performance.now()
    const timer = setInterval(() => setElapsedSeconds(Math.floor((performance.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [])

  return <>
    <p role="status">Verifying local processing packages, media tools, and the speech model.</p>
    <small>{elapsedSeconds}s elapsed · Up to 60 seconds. No downloads or installations.</small>
  </>
}
