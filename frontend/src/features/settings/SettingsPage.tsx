import { MediaSettingsSections } from './MediaSettingsSections'
import { RuntimeSettingsSection } from './RuntimeSettingsSection'
import { ExternalLink, FolderOpen, Heart, RotateCcw, Save } from 'lucide-react'
import { PageHeading } from '../../components/ui/PageHeading'
import type { Capabilities, Settings } from '../../types/domain'
import { SettingsSection } from './SettingsControls'
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

        <MediaSettingsSections settings={settings} capabilities={capabilities} setGroup={setGroup} />
        <RuntimeSettingsSection settings={settings} controller={controller} capabilities={capabilities} checkingSystem={checkingSystem} onCheckSystem={onCheckSystem} />

        <SettingsSection title="About" description="Desktop application identity">
          <div className="about-setting">
            <strong>{APPLICATION_DISPLAY_NAME} 1.4.0</strong>
            <span>Electron desktop · local processing · Windows</span>
          </div>
        </SettingsSection>

        <SettingsSection title="Onboarding" description="Replay the guided setup whenever you need it">
          <div className="about-setting">
            <strong>Redo onboarding</strong>
            <span>Start again at Welcome while keeping your saved dictionary, folders, and processing preferences.</span>
          </div>
          <button className="button secondary" onClick={onOpenOnboarding}>Redo onboarding</button>
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
