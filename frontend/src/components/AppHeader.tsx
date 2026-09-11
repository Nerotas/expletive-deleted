import {
  AlertCircle,
  BookOpen,
  ListVideo,
  LoaderCircle,
  MoonIcon,
  Settings as SettingsIcon,
  ShieldCheck,
  SunIcon,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import appIconUrl from '../assets/expletive-deleted-icon.svg'
import { APPLICATION_DISPLAY_NAME } from '../constants/application'
import type { Capabilities, InstallStatus, Theme } from '../types/domain'

type AppHeaderProps = {
  capabilities: Capabilities | null
  checking: boolean
  installState: InstallStatus | null
  theme: Theme
  toggleTheme: () => void
  onOpenInstall: () => void
}

function readinessLabel(capabilities: Capabilities | null) {
  if (capabilities?.processing_ready ?? capabilities?.ready) return 'System ready'
  if (capabilities?.app_runtime === 'invalid') return 'App repair needed'
  if (!capabilities?.whisper || !capabilities?.ffmpeg || !capabilities?.ffprobe) return 'Setup required'
  if (capabilities?.speech_model && capabilities.speech_model !== 'ready') return 'Download speech model'
  return 'Setup required'
}

export function AppHeader({
  capabilities,
  checking,
  installState,
  theme,
  toggleTheme,
  onOpenInstall,
}: AppHeaderProps) {
  const processingReady = capabilities?.processing_ready ?? capabilities?.ready
  const label = readinessLabel(capabilities)
  return (
    <header className="app-header">
      <div className="brand-lockup">
        <img className="brand-mark" src={appIconUrl} alt="" />
        <div>
          <strong>{APPLICATION_DISPLAY_NAME}</strong>
          <small>Censor profanity in local files.</small>
        </div>
      </div>
      <nav className="top-nav" aria-label="Application pages">
        <NavLink to="/" end><ListVideo size={17} />Queue</NavLink>
        <NavLink to="/dictionary"><BookOpen size={17} />Dictionary</NavLink>
        <NavLink to="/settings"><SettingsIcon size={17} />Settings</NavLink>
      </nav>
      <div className="header-status">
        <button
          className="theme-toggle"
          title={`Switch to ${theme === 'light' ? 'night' : 'light'} mode`}
          aria-label={`Switch to ${theme === 'light' ? 'night' : 'light'} mode`}
          onClick={toggleTheme}
        >
          {theme === 'light' ? <MoonIcon size={16} /> : <SunIcon size={16} />}
        </button>
        {installState && ['running', 'canceling'].includes(installState.status) ? (
          <button className="runtime-pill installing" type="button" onClick={onOpenInstall}>
            <LoaderCircle className="spin" size={16} />
            {installState.message || 'Installing…'}
          </button>
        ) : (
          <div className={`runtime-pill ${checking ? 'checking' : processingReady ? 'ready' : 'attention'}`}>
            {checking
              ? <LoaderCircle className="spin" size={16} />
              : processingReady
                ? <ShieldCheck size={16} />
                : <AlertCircle size={16} />}
            {checking ? 'Checking system' : label}
          </div>
        )}
      </div>
    </header>
  )
}
