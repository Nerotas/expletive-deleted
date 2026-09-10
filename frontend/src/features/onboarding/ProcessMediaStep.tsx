import { Check } from 'lucide-react'
import type { Capabilities, Settings } from '../../types/domain'
import type { QueueController } from '../queue/useQueue'
import { OnboardingStepHeading } from './OnboardingStepHeading'
import { FirstFileCard } from './FirstFileCard'
import { WorkflowInstructionCard } from './WorkflowInstructionCard'

type ProcessMediaStepProps = {
  source: string | null
  queue: QueueController
  settings: Settings
  capabilities: Capabilities | null
}

export function ProcessMediaStep({ source, queue, settings, capabilities }: ProcessMediaStepProps) {
  const ready = capabilities?.processing_ready ?? capabilities?.ready ?? false
  const setupDetail = capabilities?.app_runtime === 'invalid'
    ? 'Repair Expletive Deleted before processing this file.'
    : capabilities?.speech_model && capabilities.speech_model !== 'ready'
      ? 'Download the speech model before processing this file.'
      : 'Finish setup before processing this file.'
  const automaticCensoring = settings.processing.auto_censor_after_transcription
  return <>
    <OnboardingStepHeading title="Process safely" subtitle="Create a transcript first, review what was found, then create and review a censored copy." />
    {source ? <FirstFileCard source={source} ready={ready} busy={queue.busy} setupDetail={setupDetail} automaticCensoring={automaticCensoring} onCreateTranscript={() => void queue.submitFile(source, 'report_only')} /> : <section className="instruction-flow two-column"><WorkflowInstructionCard number="1" title="Create a transcript" description="In Queue, select a file and choose Transcribe only. This creates a transcript without changing the media." /><WorkflowInstructionCard number="2" title="Review the words" description="Open Dictionary to mark detected words as Censor or Ignore before making a copy." /></section>}
    <ol className="workflow-steps"><li><strong>Review the transcript</strong><span>Automatic recognition is helpful but not perfect. Check words and timing before sharing.</span></li><li><strong>Create censored copy</strong><span>{automaticCensoring ? 'Your selected automatic workflow queues this after verified transcription.' : 'Choose this action in Queue after you have reviewed the transcript.'}</span></li><li><strong>Review the result</strong><span>Listen or watch the finished file before sharing it with your family.</span></li><li><strong>Find your files</strong><span>Ready holds working files, Finished holds verified copies, and Processed holds originals only when you opt in.</span></li></ol>
    <p className="onboarding-caution"><Check size={15} /> Failed and cancelled work retains the original. A finished copy never replaces it.</p>
  </>
}
