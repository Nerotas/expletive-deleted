import { Check, FileText } from 'lucide-react'
import type { Capabilities, Settings } from '../../types/domain'
import type { QueueController } from '../queue/useQueue'
import { OnboardingStepHeading } from './OnboardingStepHeading'

type ProcessMediaStepProps = {
  source: string | null
  queue: QueueController
  settings: Settings
  capabilities: Capabilities | null
}

export function ProcessMediaStep({ source, queue, settings, capabilities }: ProcessMediaStepProps) {
  const ready = Boolean(capabilities?.ready)
  const automaticCensoring = settings.processing.auto_censor_after_transcription
  return <>
    <OnboardingStepHeading title="Process safely" subtitle="Create a transcript first, review what was found, then create and review a censored copy." />
    {source ? <section className="onboarding-first-file" aria-labelledby="first-file-title">
      <h3 id="first-file-title">Your first file is ready</h3><p>{source}</p>
      {!ready && <p className="onboarding-caution">Finish the required component setup before processing this file.</p>}
      <button className="button primary" disabled={!ready || queue.busy} onClick={() => void queue.submitFile(source, 'report_only')}><FileText size={16} />Create transcript</button>
      <p className="onboarding-helper">{automaticCensoring ? 'After a verified transcript, your chosen workflow queues a censored copy automatically.' : 'After the transcript is ready, open Dictionary to review detected words, then select Create censored copy in Queue.'}</p>
    </section> : <section className="instruction-flow two-column"><article><span>1</span><h3>Create a transcript</h3><p>In Queue, select a file and choose Transcribe only. This creates a transcript without changing the media.</p></article><article><span>2</span><h3>Review the words</h3><p>Open Dictionary to mark detected words as Censor or Ignore before making a copy.</p></article></section>}
    <ol className="workflow-steps"><li><strong>Review the transcript</strong><span>Automatic recognition is helpful but not perfect. Check words and timing before sharing.</span></li><li><strong>Create censored copy</strong><span>{automaticCensoring ? 'Your selected automatic workflow queues this after verified transcription.' : 'Choose this action in Queue after you have reviewed the transcript.'}</span></li><li><strong>Review the result</strong><span>Listen or watch the finished file before sharing it with your family.</span></li><li><strong>Find your files</strong><span>Ready holds working files, Finished holds verified copies, and Processed holds originals only when you opt in.</span></li></ol>
    <p className="onboarding-caution"><Check size={15} /> Failed and cancelled work retains the original. A finished copy never replaces it.</p>
  </>
}
