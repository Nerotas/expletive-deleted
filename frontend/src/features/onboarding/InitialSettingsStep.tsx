import { Check, FolderOpen } from 'lucide-react'
import { SegmentedControl } from '../../components/ui/SegmentedControl'
import type { Settings } from '../../types/domain'
import type { DictionaryController } from '../dictionary/useDictionary'
import { OnboardingStepHeading } from './OnboardingStepHeading'

const DIRECTORY_LABELS: Record<keyof Settings['directories'], { title: string; detail: string }> = {
  input: { title: 'Ready / Input', detail: 'Media waiting to be processed' },
  output: { title: 'Finished / Output', detail: 'Verified censored copies' },
  archive: { title: 'Processed / Archive', detail: 'Originals archived only after success' },
  transcripts: { title: 'Transcripts', detail: 'Reusable local transcripts' },
}

type InitialSettingsStepProps = {
  draft: Settings
  dictionary: DictionaryController
  dictionaryPrepared: boolean
  onDictionaryPrepared: () => void
  onChange: <K extends keyof Settings>(group: K, value: Settings[K]) => void
  onChooseDirectory: (key: keyof Settings['directories']) => void
}

export function InitialSettingsStep({
  draft,
  dictionary,
  dictionaryPrepared,
  onDictionaryPrepared,
  onChange,
  onChooseDirectory,
}: InitialSettingsStepProps) {
  return <>
    <OnboardingStepHeading title="Choose your settings" subtitle="These are your starting choices. You can change them later in Settings; nothing starts processing when you save this page." />
    <section className="onboarding-setting-section" aria-labelledby="dictionary-setup-title">
      <div className="onboarding-section-heading"><h3 id="dictionary-setup-title">Words to censor</h3><p>Choose the starting point for your private dictionary.</p></div>
      <div className="onboarding-choices two-column">
        <button className={dictionaryPrepared ? 'selected' : undefined} disabled={dictionary.busy} onClick={onDictionaryPrepared}>
          <strong>Keep my current dictionary</strong>
          <span>Use the words and exclusions already saved on this computer.</span>
        </button>
        <button disabled={dictionary.busy} onClick={async () => {
          if (await dictionary.restoreDefaults()) onDictionaryPrepared()
        }}>
          <strong>Use default censored words</strong>
          <span>Replace the local censored-word list with the included default list. Personal exclusions are not added.</span>
        </button>
        <button disabled={dictionary.busy} onClick={async () => {
          if (await dictionary.importDictionary()) onDictionaryPrepared()
        }}>
          <strong>Import a dictionary</strong>
          <span>Choose a validated combined dictionary file. If importing fails, your current words stay unchanged.</span>
        </button>
      </div>
      {dictionaryPrepared && <p className="selection-confirmation"><Check size={15} />Dictionary choice ready</p>}
    </section>

    <section className="onboarding-setting-section" aria-labelledby="censoring-setup-title">
      <div className="onboarding-section-heading"><h3 id="censoring-setup-title">How to cover the language</h3><p>Review every finished file, whichever choice you make.</p></div>
      <SegmentedControl label="Censoring method" value={draft.censoring.stereo_method} options={[["drop_audio", 'Drop audio'], ['karaoke', 'Karaoke']]} onChange={(stereo_method) => onChange('censoring', { ...draft.censoring, stereo_method })} />
      <div className="method-details two-column">
        <article className={draft.censoring.stereo_method === 'drop_audio' ? 'selected' : undefined}><h3>Drop audio</h3><p>Silences all sound during each detected word. It works with mono and stereo files and gives the most predictable result.</p><strong>Recommended for reliable obscuring</strong></article>
        <article className={draft.censoring.stereo_method === 'karaoke' ? 'selected' : undefined}><h3>Karaoke</h3><p>Attempts to reduce centered dialogue while keeping some music and effects. Results depend on the mix; off-center speech may remain.</p><strong>Not suitable for mono audio</strong></article>
      </div>
    </section>

    <AutomationChoices draft={draft} onChange={onChange} />

    <section className="onboarding-setting-section" aria-labelledby="folder-setup-title">
      <div className="onboarding-section-heading"><h3 id="folder-setup-title">Working folders</h3><p>They must be separate absolute paths. The app creates missing folders only when you save these settings.</p></div>
      <div className="onboarding-folders">
        {(Object.keys(draft.directories) as Array<keyof Settings['directories']>).map((key) => <label key={key}>
          <span><strong>{DIRECTORY_LABELS[key].title}</strong><small>{DIRECTORY_LABELS[key].detail}</small></span>
          <div><input aria-label={DIRECTORY_LABELS[key].title} value={draft.directories[key]} onChange={(event) => onChange('directories', { ...draft.directories, [key]: event.target.value })} />
            <button className="icon-button" type="button" title={`Choose ${DIRECTORY_LABELS[key].title}`} aria-label={`Choose ${DIRECTORY_LABELS[key].title}`} onClick={() => onChooseDirectory(key)}><FolderOpen size={17} /></button>
          </div>
        </label>)}
      </div>
      <label className="toggle-row onboarding-archive"><div><strong>Archive originals after verified success</strong><span>Off by default. A failure or cancellation always retains the original.</span></div><input type="checkbox" checked={draft.source.archive_after_success} onChange={(event) => onChange('source', { ...draft.source, archive_after_success: event.target.checked })} /></label>
    </section>
  </>
}

function AutomationChoices({ draft, onChange }: Pick<InitialSettingsStepProps, 'draft' | 'onChange'>) {
  return <section className="onboarding-setting-section" aria-labelledby="automation-setup-title">
    <div className="onboarding-section-heading"><h3 id="automation-setup-title">Choose your workflow</h3><p>Both options are off until you choose them. Saving a choice never starts files already in Ready.</p></div>
    <label className="toggle-row onboarding-automation"><div><strong>Automatically create a censored copy after transcription</strong><span>After a new transcript is verified, the app queues a censored copy without a manual pause. You can keep this off to review the transcript first.</span></div><input type="checkbox" checked={draft.processing.auto_censor_after_transcription} onChange={(event) => onChange('processing', { ...draft.processing, auto_censor_after_transcription: event.target.checked })} /></label>
    <label className="toggle-row onboarding-automation"><div><strong>Automatically process YouTube downloads</strong><span>Each completed YouTube download goes to Ready, then transcription, then the censored-copy queue. This requires optional yt-dlp and network access; local files do not need it.</span></div><input type="checkbox" checked={draft.processing.auto_transcode_youtube_downloads} onChange={(event) => onChange('processing', { ...draft.processing, auto_transcode_youtube_downloads: event.target.checked })} /></label>
  </section>
}
