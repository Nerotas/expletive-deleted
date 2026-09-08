import { OnboardingStepHeading } from './OnboardingStepHeading'
import type { Capabilities, Settings } from '../../types/domain'

type FinishStepProps = {
  settings: Settings
  capabilities: Capabilities | null
  dictionaryPrepared: boolean
}

export function FinishStep({ settings, capabilities, dictionaryPrepared }: FinishStepProps) {
  return <>
    <OnboardingStepHeading title="Ready when you are" subtitle="Review your choices, then finish setup. You can return to this walkthrough from Settings." />
    <dl className="finish-summary">
      <div><dt>Required components</dt><dd>{capabilities?.ready ? 'Verified' : 'Needs attention before processing'}</dd></div>
      <div><dt>Dictionary</dt><dd>{dictionaryPrepared ? 'Choice prepared' : 'Not prepared'}</dd></div>
      <div><dt>Covering method</dt><dd>{settings.censoring.stereo_method === 'drop_audio' ? 'Drop audio' : 'Karaoke'}</dd></div>
      <div><dt>After transcription</dt><dd>{settings.processing.auto_censor_after_transcription ? 'Automatically queue a censored copy' : 'Pause for transcript review'}</dd></div>
      <div><dt>YouTube downloads</dt><dd>{settings.processing.auto_transcode_youtube_downloads ? 'Transcribe and queue a censored copy automatically' : 'Manual workflow'}</dd></div>
      <div><dt>Ready folder</dt><dd>{settings.directories.input}</dd></div>
      <div><dt>Originals</dt><dd>{settings.source.archive_after_success ? 'Archive after a verified censored copy' : 'Keep in Ready'}</dd></div>
    </dl>
    <p className="onboarding-caution">Finish saves these choices and records that you completed the walkthrough. It does not begin processing media or bypass future system checks.</p>
  </>
}
