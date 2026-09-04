import { AlertCircle, CheckCircle2, ExternalLink, FileSearch, FolderOpen, Heart, RefreshCw, RotateCcw, Save } from 'lucide-react'
import { NumberInput } from '../../components/ui/NumberInput'
import { PageHeading } from '../../components/ui/PageHeading'
import { SegmentedControl } from '../../components/ui/SegmentedControl'
import type { Capabilities, Settings, WhisperModel } from '../../types/domain'
import { Field, SettingsSection } from './SettingsControls'
import type { SettingsController } from './useSettingsController'
import './settings.css'
import { APPLICATION_DISPLAY_NAME } from '../../constants/application'
import { desktopClient } from '../../services/desktop-client'

const SUPPORT_URL = 'https://ko-fi.com/nicholaserotas'

type SettingsPageProps = {
  controller: SettingsController
  capabilities: Capabilities | null
  checkingSystem: boolean
  onCheckSystem: () => void
  onOpenOnboarding: () => void
}

const DIRECTORY_LABELS: Record<keyof Settings['directories'], string> = {
  input: 'Ready / Input',
  output: 'Finished / Output',
  archive: 'Processed / Archive',
  transcripts: 'Transcripts',
}

export function SettingsPage({ controller, capabilities, checkingSystem, onCheckSystem, onOpenOnboarding }: SettingsPageProps) {
  const settings = controller.draft
  if (!settings) return <div className="loading-row">Loading settings</div>

  const setGroup = <K extends keyof Settings>(group: K, value: Settings[K]) => {
    controller.updateGroup(group, value)
  }

  return (
    <section className="page settings-page">
      <PageHeading title="Settings" subtitle="Persistent preferences for local processing">
        <button
          className="button secondary"
          disabled={controller.busy || !controller.dirty}
          onClick={controller.discard}
        >
          <RotateCcw size={17} />Discard
        </button>
        <button
          className="button primary"
          disabled={controller.busy || !controller.dirty}
          onClick={() => void controller.save()}
        >
          <Save size={17} />Save changes
        </button>
      </PageHeading>

      <div className="settings-layout">
        <SettingsSection title="Directories" description="User-owned working folders">
          {(Object.keys(settings.directories) as Array<keyof Settings['directories']>).map((key) => (
            <label className="path-field" key={key}>
              <span>{DIRECTORY_LABELS[key]}</span>
              <div>
                <input
                  value={settings.directories[key]}
                  onChange={(event) => setGroup('directories', {
                    ...settings.directories,
                    [key]: event.target.value,
                  })}
                />
                <button
                  className="icon-button"
                  title={`Choose ${key} directory`}
                  onClick={() => void controller.chooseDirectory(key)}
                >
                  <FolderOpen size={17} />
                </button>
              </div>
            </label>
          ))}
        </SettingsSection>

        <SettingsSection title="Processing" description="Choose the workflow and compute device">
          <Field label="Mode">
            <SegmentedControl
              label="Processing mode"
              value={settings.processing.mode}
              options={[["report_only", 'Report only'], ['censor', 'Censor media']]}
              onChange={(mode) => setGroup('processing', { ...settings.processing, mode })}
            />
          </Field>
          <Field label="Device">
            <select
              aria-label="Device"
              value={settings.processing.device}
              onChange={(event) => setGroup('processing', {
                ...settings.processing,
                device: event.target.value as Settings['processing']['device'],
              })}
            >
              <option value="auto">Automatic ({capabilities?.whisper_device ?? 'detecting'})</option>
              <option value="cpu">CPU</option>
              <option value="cuda">CUDA</option>
            </select>
          </Field>
        </SettingsSection>

        <SettingsSection title="Censoring" description="Audio treatment and interval timing">
          <Field label="Stereo method">
            <SegmentedControl
              label="Stereo method"
              value={settings.censoring.stereo_method}
              options={[["drop_audio", 'Drop audio'], ['karaoke', 'Karaoke']]}
              onChange={(stereo_method) => setGroup('censoring', {
                ...settings.censoring,
                stereo_method,
              })}
            />
          </Field>
          <div className="field-pair">
            <Field label="Before word">
              <NumberInput
                label="Before word"
                value={settings.censoring.padding_before_ms}
                onChange={(padding_before_ms) => setGroup('censoring', {
                  ...settings.censoring,
                  padding_before_ms,
                })}
              />
            </Field>
            <Field label="After word">
              <NumberInput
                label="After word"
                value={settings.censoring.padding_after_ms}
                onChange={(padding_after_ms) => setGroup('censoring', {
                  ...settings.censoring,
                  padding_after_ms,
                })}
              />
            </Field>
          </div>
        </SettingsSection>

        <SettingsSection title="Output" description="Audio layout and source safety">
          <Field label="Surround audio">
            <SegmentedControl
              label="Surround audio"
              value={settings.audio.surround_output}
              options={[["preserve_5_1", 'Preserve 5.1'], ['downmix_stereo', 'Downmix to stereo']]}
              onChange={(surround_output) => setGroup('audio', { surround_output })}
            />
          </Field>
          <div className="output-note">
            <strong>Video is preserved</strong>
            <span>The source video stream is copied unchanged into the MKV output.</span>
          </div>
          <label className="toggle-row">
            <div>
              <strong>Scan subdirectories</strong>
              <span>Include supported media inside folders under Ready.</span>
            </div>
            <input
              type="checkbox"
              checked={settings.source.scan_subdirectories}
              onChange={(event) => setGroup('source', {
                ...settings.source,
                scan_subdirectories: event.target.checked,
              })}
            />
          </label>
          <label className="toggle-row">
            <div>
              <strong>Archive original after success</strong>
              <span>Off by default. Never moves source files after failure or cancellation.</span>
            </div>
            <input
              type="checkbox"
              checked={settings.source.archive_after_success}
              onChange={(event) => setGroup('source', {
                ...settings.source,
                archive_after_success: event.target.checked,
              })}
            />
          </label>
        </SettingsSection>

        <SettingsSection title="Whisper" description="Choose the accuracy and speed profile for transcription">
          <Field label="Model">
            <select
              aria-label="Model"
              value={settings.whisper.model}
              onChange={(event) => setGroup('whisper', {
                ...settings.whisper,
                model: event.target.value as WhisperModel,
              })}
            >
              <option value="large-v3">large-v3 — recommended, highest accuracy</option>
              <option value="medium">medium — faster, lower accuracy</option>
              <option value="small">small — substantially lower accuracy</option>
              <option value="base">base — major accuracy tradeoff</option>
              <option value="tiny">tiny — fastest, lowest accuracy</option>
            </select>
          </Field>
          <div className={`whisper-notice ${settings.whisper.model === 'large-v3' ? 'recommended' : 'warning'}`}>
            <AlertCircle size={17} />
            <div>
              <strong>
                {settings.whisper.model === 'large-v3'
                  ? 'Recommended for reliable censoring'
                  : `${settings.whisper.model} trades accuracy for speed`}
              </strong>
              <span>
                {settings.whisper.model === 'large-v3'
                  ? 'large-v3 remains the default because it produces the most consistent word detection and timestamps.'
                  : 'Quality and timestamp accuracy drop noticeably with smaller models. Review transcripts and discovered words carefully.'}
              </span>
            </div>
          </div>
          <small className="whisper-library-note">
            faster-whisper is used for all transcription. Changing the model requires its local
            component download, and existing transcripts from another model will be regenerated.
          </small>
        </SettingsSection>

        <SettingsSection title="Runtime components" description="Automatic discovery and optional path overrides">
          <label className="path-field">
            <span>FFmpeg path override</span>
            <div>
              <input
                value={settings.runtime.ffmpeg_path ?? ''}
                placeholder="Using automatic detection"
                onChange={(event) => setGroup('runtime', {
                  ...settings.runtime,
                  ffmpeg_path: event.target.value || null,
                })}
              />
              <button className="icon-button" title="Choose and verify FFmpeg" onClick={() => void controller.chooseFfmpeg()}>
                <FileSearch size={17} />
              </button>
            </div>
          </label>
          <label className="path-field">
            <span>FFprobe path override</span>
            <input
              value={settings.runtime.ffprobe_path ?? ''}
              placeholder="Using automatic detection"
              onChange={(event) => setGroup('runtime', {
                ...settings.runtime,
                ffprobe_path: event.target.value || null,
              })}
            />
          </label>
          <label className="path-field">
            <span>Whisper cache override</span>
            <div>
              <input
                value={settings.runtime.whisper_cache ?? ''}
                placeholder="Using application-managed cache"
                onChange={(event) => setGroup('runtime', {
                  ...settings.runtime,
                  whisper_cache: event.target.value || null,
                })}
              />
              <button className="icon-button" title="Choose Whisper model cache" onClick={() => void controller.chooseWhisperCache()}>
                <FolderOpen size={17} />
              </button>
            </div>
          </label>
          <div className={`runtime-status ${capabilities?.ready ? 'ready' : 'attention'}`}>
            {capabilities?.ready ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
            <span>{capabilities?.ready ? 'All required components are verified.' : 'One or more required components need attention.'}</span>
            <button className="button secondary" disabled={checkingSystem} onClick={onCheckSystem}>
              <RefreshCw className={checkingSystem ? 'spin' : undefined} size={15} />Check system
            </button>
          </div>
          <small className="whisper-library-note">
            Leave overrides blank to use automatically detected components. These fields select
            executable or cache locations; they do not add FFmpeg command-line flags. Save changed
            paths before checking again.
          </small>
        </SettingsSection>

        <SettingsSection title="About" description="Desktop application identity">
          <div className="about-setting">
            <strong>{APPLICATION_DISPLAY_NAME} 1.0.1</strong>
            <span>Electron desktop · local processing · Windows</span>
          </div>
          <button className="button secondary" onClick={onOpenOnboarding}>Open setup walkthrough</button>
        </SettingsSection>

        <SettingsSection title="Support" description="Help sustain future development">
          <div className="support-setting">
            <Heart size={20} aria-hidden="true" />
            <div>
              <strong>Support Expletive Deleted on Ko-fi</strong>
              <span>Optional support does not unlock features or priority service.</span>
            </div>
          </div>
          <button className="button secondary" onClick={() => void desktopClient.openExternal(SUPPORT_URL)}>
            Support development<ExternalLink size={15} aria-hidden="true" />
          </button>
        </SettingsSection>
      </div>
    </section>
  )
}
