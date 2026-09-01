import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileAudio,
  FolderOpen,
  ListChecks,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { SegmentedControl } from '../../components/ui/SegmentedControl'
import { desktopClient } from '../../services/desktop-client'
import type { Capabilities, Settings } from '../../types/domain'
import type { DictionaryController } from '../dictionary/useDictionary'
import type { SettingsController } from '../settings/useSettingsController'
import './onboarding.css'

const STEPS = [
  'Welcome',
  'Components',
  'Dictionary',
  'Censoring',
  'Folders',
  'Add media',
  'Process media',
  'Finish',
] as const

const DIRECTORY_LABELS: Record<keyof Settings['directories'], { title: string; detail: string }> = {
  input: { title: 'Ready / Input', detail: 'Media waiting to be processed' },
  output: { title: 'Finished / Output', detail: 'Verified censored copies' },
  archive: { title: 'Processed / Archive', detail: 'Originals archived only after success' },
  transcripts: { title: 'Transcripts', detail: 'Reusable local transcripts' },
}

type OnboardingPageProps = {
  settings: SettingsController
  capabilities: Capabilities | null
  checking: boolean
  capabilityBusy: boolean
  dictionary: DictionaryController
  onReviewInstall: (components: string[]) => void
  onLocateExisting: (component: 'ffmpeg' | 'whisper_model') => void
  onCheckAgain: () => void
  onFinished: () => void
  onError: (message: string) => void
}

export function OnboardingPage({
  settings,
  capabilities,
  checking,
  capabilityBusy,
  dictionary,
  onReviewInstall,
  onLocateExisting,
  onCheckAgain,
  onFinished,
  onError,
}: OnboardingPageProps) {
  const initialSettings = settings.draft
  const [step, setStep] = useState(0)
  const [draft, setDraft] = useState<Settings | null>(initialSettings)
  const [dictionaryPrepared, setDictionaryPrepared] = useState(
    initialSettings?.onboarding.completed ?? false,
  )
  const [saving, setSaving] = useState(false)

  if (!draft) return <div className="loading-row">Loading setup</div>
  const currentDraft = draft
  const requiredComponentsReady = Boolean(
    capabilities?.ffmpeg
    && capabilities.ffprobe
    && capabilities.whisper
    && capabilities.whisper_model_ready
    && capabilities.whisper_model === 'large-v3',
  )

  const updateDraft = <K extends keyof Settings>(group: K, value: Settings[K]) => {
    setDraft((current) => current ? { ...current, [group]: value } : current)
  }

  const saveAndAdvance = async () => {
    if (step === 1 && !requiredComponentsReady) return
    if (step === 2 && !dictionaryPrepared) return
    setSaving(true)
    const saved = await settings.saveDraft(draft)
    setSaving(false)
    if (saved) setStep((current) => Math.min(current + 1, STEPS.length - 1))
  }

  const chooseDirectory = async (key: keyof Settings['directories']) => {
    try {
      const selected = await desktopClient.selectDirectory(draft.directories[key])
      if (selected) updateDraft('directories', { ...draft.directories, [key]: selected })
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  const finish = async () => {
    setSaving(true)
    const saved = await settings.saveDraft({
      ...draft,
      onboarding: { completed: true },
    })
    setSaving(false)
    if (saved) onFinished()
  }

  return (
    <section className="page onboarding-page" aria-labelledby="onboarding-title">
      <aside className="onboarding-rail">
        <span className="eyebrow">First-run setup</span>
        <h1 id="onboarding-title">Make it yours</h1>
        <ol>
          {STEPS.map((label, index) => (
            <li key={label} className={index === step ? 'active' : index < step ? 'complete' : undefined}>
              <span>{index < step ? <Check size={13} /> : index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
        <small>Your choices stay on this computer.</small>
      </aside>

      <div className="onboarding-workspace">
        <div className="onboarding-step">{renderStep()}</div>
        <footer className="onboarding-actions">
          <button
            className="button secondary"
            disabled={step === 0 || saving}
            onClick={() => setStep((current) => current - 1)}
          >
            <ArrowLeft size={16} />Back
          </button>
          <span>{`Step ${step + 1} of ${STEPS.length}`}</span>
          {step === STEPS.length - 1 ? (
            <button className="button primary" disabled={saving} onClick={() => void finish()}>
              <ShieldCheck size={16} />Finish setup
            </button>
          ) : (
            <button
              className="button primary"
              disabled={saving || (step === 1 && !requiredComponentsReady) || (step === 2 && !dictionaryPrepared)}
              onClick={() => void saveAndAdvance()}
            >
              Continue<ArrowRight size={16} />
            </button>
          )}
        </footer>
      </div>
    </section>
  )

  function renderStep() {
    switch (step) {
      case 0:
        return (
          <>
            <StepHeading title="Welcome to Expletive Deleted" subtitle="A short setup for private, reviewable media processing." />
            <div className="onboarding-lead">
              <ShieldCheck size={34} />
              <div>
                <strong>Your media stays local</strong>
                <p>Media and transcripts are not uploaded. Originals are retained by default, and finished files should always be reviewed before sharing.</p>
              </div>
            </div>
            <div className="onboarding-summary">
              <SummaryItem icon={<ListChecks />} title="Prepare" detail="Verify required components and your dictionary." />
              <SummaryItem icon={<FileAudio />} title="Choose" detail="Select censoring behavior and working folders." />
              <SummaryItem icon={<Check />} title="Learn" detail="See how to add, transcribe, review, and censor media." />
            </div>
            <p className="onboarding-caution">Automated transcription and censorship are not perfect. Review the transcript and finished media.</p>
          </>
        )
      case 1:
        return (
          <>
            <StepHeading title="Prepare required components" subtitle="Each component is checked independently. Nothing is downloaded without your approval." />
            <div className="component-list">
              <ComponentRow
                title="FFmpeg and FFprobe"
                detail="Inspect media and create the censored output file."
                ready={Boolean(capabilities?.ffmpeg && capabilities?.ffprobe)}
                checking={checking}
                busy={capabilityBusy}
                onLocate={() => onLocateExisting('ffmpeg')}
                onGet={() => onReviewInstall(['ffmpeg'])}
              />
              <ComponentRow
                title="Speech recognition"
                detail="faster-whisper and its Python packages transcribe spoken language locally."
                ready={Boolean(capabilities?.whisper)}
                checking={checking}
                busy={capabilityBusy}
                onGet={() => onReviewInstall(['python'])}
              />
              <ComponentRow
                title="Whisper large-v3 model"
                detail="The supported accuracy baseline for word recognition and timing. It is a separate, substantial download."
                ready={Boolean(capabilities?.whisper_model_ready && capabilities.whisper_model === 'large-v3')}
                checking={checking}
                busy={capabilityBusy}
                onLocate={() => onLocateExisting('whisper_model')}
                onGet={capabilities?.whisper ? () => onReviewInstall(['whisper_model']) : undefined}
              />
            </div>
            <button className="button secondary check-components" disabled={capabilityBusy} onClick={onCheckAgain}>
              <RefreshCw className={checking ? 'spin' : undefined} size={16} />Check again
            </button>
          </>
        )
      case 2:
        return (
          <>
            <StepHeading title="Prepare your dictionary" subtitle="Choose a starting point for words that should be censored." />
            <div className="onboarding-choices two-column">
              <button
                className={dictionaryPrepared ? 'selected' : undefined}
                disabled={dictionary.busy}
                onClick={async () => {
                  await dictionary.restoreDefaults()
                  setDictionaryPrepared(true)
                }}
              >
                <strong>Use default censored words</strong>
                <span>Initialize the local censored-word store. Personal exclusions are never included.</span>
              </button>
              <button
                disabled={dictionary.busy}
                onClick={async () => {
                  const imported = await dictionary.importDictionary()
                  if (imported) setDictionaryPrepared(true)
                }}
              >
                <strong>Import a dictionary</strong>
                <span>Select a validated combined dictionary file. A failed import leaves current words untouched.</span>
              </button>
            </div>
            {dictionaryPrepared && <p className="selection-confirmation"><Check size={15} />Dictionary prepared</p>}
          </>
        )
      case 3:
        return (
          <>
            <StepHeading title="Choose a censoring method" subtitle="Neither method guarantees perfect censorship. Review every finished file." />
            <SegmentedControl
              label="Censoring method"
              value={currentDraft.censoring.stereo_method}
              options={[["drop_audio", 'Drop audio'], ['karaoke', 'Karaoke']]}
              onChange={(stereo_method) => updateDraft('censoring', { ...currentDraft.censoring, stereo_method })}
            />
            <div className="method-details two-column">
              <article className={currentDraft.censoring.stereo_method === 'drop_audio' ? 'selected' : undefined}>
                <h3>Drop audio</h3>
                <p>Silences the complete mix during each detected interval. It is predictable, works with mono and stereo, and removes dialogue, music, and effects.</p>
                <strong>Recommended for reliable obscuring</strong>
              </article>
              <article className={currentDraft.censoring.stereo_method === 'karaoke' ? 'selected' : undefined}>
                <h3>Karaoke</h3>
                <p>Attempts to cancel centered dialogue while retaining some music and effects. Results depend on the stereo mix and off-center speech may remain.</p>
                <strong>Not appropriate for mono audio</strong>
              </article>
            </div>
          </>
        )
      case 4:
        return (
          <>
            <StepHeading title="Confirm working folders" subtitle="Folders must be absolute and distinct. Missing folders are created only when these settings are saved." />
            <div className="onboarding-folders">
              {(Object.keys(currentDraft.directories) as Array<keyof Settings['directories']>).map((key) => (
                <label key={key}>
                  <span><strong>{DIRECTORY_LABELS[key].title}</strong><small>{DIRECTORY_LABELS[key].detail}</small></span>
                  <div>
                    <input value={currentDraft.directories[key]} onChange={(event) => updateDraft('directories', { ...currentDraft.directories, [key]: event.target.value })} />
                    <button className="icon-button" title={`Choose ${DIRECTORY_LABELS[key].title}`} onClick={() => void chooseDirectory(key)}>
                      <FolderOpen size={17} />
                    </button>
                  </div>
                </label>
              ))}
            </div>
            <label className="toggle-row onboarding-archive">
              <div><strong>Archive originals after verified success</strong><span>Off by default. Failures and cancellations always retain the original.</span></div>
              <input type="checkbox" checked={currentDraft.source.archive_after_success} onChange={(event) => updateDraft('source', { ...currentDraft.source, archive_after_success: event.target.checked })} />
            </label>
          </>
        )
      case 5:
        return (
          <>
            <StepHeading title="Add media to Ready" subtitle="Adding files never starts processing automatically." />
            <div className="instruction-flow two-column">
              <article><span>1</span><h3>Ready folder</h3><p>Place supported audio or video in Ready. Subfolders are included when subdirectory scanning is enabled.</p></article>
              <article><span>2</span><h3>Drag and drop</h3><p>Drop files into Queue, then confirm the copy. Originals stay where they are; unsupported files and collisions are rejected.</p></article>
            </div>
          </>
        )
      case 6:
        return (
          <>
            <StepHeading title="Transcribe, review, then censor" subtitle="Jobs run one at a time in queue order." />
            <ol className="workflow-steps">
              <li><strong>Transcribe only</strong><span>Create and verify a transcript without media output.</span></li>
              <li><strong>Review Dictionary</strong><span>Classify discovered words as Censor or Ignore.</span></li>
              <li><strong>Transcribe + Transcode</strong><span>Create a censored copy, reusing a compatible verified transcript when available.</span></li>
              <li><strong>Review the result</strong><span>Check the finished media before sharing it.</span></li>
            </ol>
            <p className="onboarding-caution">Retranscribe replaces a transcript while retaining finished media. Retranscode replaces finished output only after the new output succeeds. Failed and cancelled jobs retain originals.</p>
          </>
        )
      default:
        return (
          <>
            <StepHeading title="Ready for your first file" subtitle="Review your setup. Live component checks continue on every launch." />
            <dl className="finish-summary">
              <div><dt>Components</dt><dd>{capabilities?.ready ? 'Verified' : 'Needs attention'}</dd></div>
              <div><dt>Dictionary</dt><dd>{dictionaryPrepared ? 'Prepared' : 'Not prepared'}</dd></div>
              <div><dt>Censoring</dt><dd>{currentDraft.censoring.stereo_method === 'drop_audio' ? 'Drop audio' : 'Karaoke'}</dd></div>
              <div><dt>Ready folder</dt><dd>{currentDraft.directories.input}</dd></div>
              <div><dt>Source archival</dt><dd>{currentDraft.source.archive_after_success ? 'After verified success' : 'Off'}</dd></div>
            </dl>
            <p className="onboarding-caution">Finishing records that you completed this walkthrough. It does not override future component checks or start processing media.</p>
          </>
        )
    }
  }
}

function StepHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return <header className="onboarding-heading"><h2>{title}</h2><p>{subtitle}</p></header>
}

function SummaryItem({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <article>{icon}<strong>{title}</strong><span>{detail}</span></article>
}

function ComponentRow({
  title,
  detail,
  ready,
  checking,
  busy,
  onLocate,
  onGet,
}: {
  title: string
  detail: string
  ready: boolean
  checking: boolean
  busy: boolean
  onLocate?: () => void
  onGet?: () => void
}) {
  return (
    <article className="component-row">
      <span className={ready ? 'ready' : undefined}>{ready ? <Check size={16} /> : '!'}</span>
      <div><strong>{title}</strong><small>{detail}</small></div>
      <b>{checking ? 'Checking' : ready ? 'Ready' : 'Missing'}</b>
      {!ready && <div className="component-actions">
        {onLocate && <button className="button secondary" disabled={busy} onClick={onLocate}>Locate existing</button>}
        {onGet && <button className="button primary" disabled={busy} onClick={onGet}>Get</button>}
      </div>}
    </article>
  )
}
