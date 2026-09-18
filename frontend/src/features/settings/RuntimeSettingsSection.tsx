import { AlertCircle, CheckCircle2, FileSearch, FolderOpen, RefreshCw } from 'lucide-react'
import type { Capabilities, Settings } from '../../types/domain'
import { SettingsSection } from './SettingsControls'
import type { SettingsController } from './useSettingsController'

type Props = {
  settings: Settings
  controller: SettingsController
  capabilities: Capabilities | null
  checkingSystem: boolean
  onCheckSystem: () => void
}

export function RuntimeSettingsSection({ settings, controller, capabilities, checkingSystem, onCheckSystem }: Props) {
  const bundledRuntime = capabilities?.app_runtime_source === 'bundled'
  const setGroup = controller.updateGroup
  return (
    <SettingsSection title="Runtime components" description={bundledRuntime ? 'Included private Python and user-approved processing components' : 'Automatic discovery and optional path overrides'}>
      {bundledRuntime && <p className="whisper-library-note">Private Python came with Expletive Deleted. Transcription packages, FFmpeg, FFprobe, YouTube tools, and speech models are installed or selected separately after your approval.</p>}
      <label className="path-field">
        <span>FFmpeg path override</span>
        <div>
          <input value={settings.runtime.ffmpeg_path ?? ''} placeholder="Using automatic detection" onChange={(event) => setGroup('runtime', { ...settings.runtime, ffmpeg_path: event.target.value || null })} />
          <button className="icon-button" title="Choose and verify FFmpeg" onClick={() => void controller.chooseFfmpeg()}><FileSearch size={17} /></button>
        </div>
      </label>
      <label className="path-field">
        <span>FFprobe path override</span>
        <input value={settings.runtime.ffprobe_path ?? ''} placeholder="Using automatic detection" onChange={(event) => setGroup('runtime', { ...settings.runtime, ffprobe_path: event.target.value || null })} />
      </label>
      <label className="path-field">
        <span>Whisper model location</span>
        <div>
          <input value={settings.runtime.whisper_cache ?? ''} placeholder="Using application-managed model location" onChange={(event) => setGroup('runtime', { ...settings.runtime, whisper_cache: event.target.value || null })} />
          <button className="icon-button" title="Choose Whisper model cache" onClick={() => void controller.chooseWhisperCache()}><FolderOpen size={17} /></button>
        </div>
      </label>
      <div className={`runtime-status ${(capabilities?.processing_ready ?? capabilities?.ready) ? 'ready' : 'attention'}`}>
        {(capabilities?.processing_ready ?? capabilities?.ready) ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
        <span>{(capabilities?.processing_ready ?? capabilities?.ready) ? 'Processing components and speech model are verified.' : capabilities?.app_runtime === 'invalid' ? 'The installed app needs repair.' : 'One or more processing components need attention.'}</span>
        <button className="button secondary" disabled={checkingSystem} onClick={onCheckSystem}><RefreshCw className={checkingSystem ? 'spin' : undefined} size={15} />Check system</button>
      </div>
      <small className="whisper-library-note">Leave overrides blank to use automatically detected components. These fields select executable or cache locations; they do not add FFmpeg command-line flags. Save changed paths before checking again.</small>
    </SettingsSection>

  )
}
