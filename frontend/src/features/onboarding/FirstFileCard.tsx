import { FileText } from 'lucide-react'

type FirstFileCardProps = {
  source: string
  ready: boolean
  busy: boolean
  setupDetail: string
  automaticCensoring: boolean
  onCreateTranscript: () => void
}

export function FirstFileCard({ source, ready, busy, setupDetail, automaticCensoring, onCreateTranscript }: FirstFileCardProps) {
  return <section className="onboarding-first-file" aria-labelledby="first-file-title">
    <h3 id="first-file-title">Your first file is ready</h3>
    <p>{source}</p>
    {!ready && <p className="onboarding-caution">{setupDetail}</p>}
    <button className="button primary" disabled={!ready || busy} onClick={onCreateTranscript}><FileText size={16} />Create transcript</button>
    <p className="onboarding-helper">{automaticCensoring ? 'After a verified transcript, your chosen workflow queues a censored copy automatically.' : 'After the transcript is ready, open Dictionary to review detected words, then select Create censored copy in Queue.'}</p>
  </section>
}