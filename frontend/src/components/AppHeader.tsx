import {
  AlertCircle,
  BookOpen,
  ListVideo,
  MoonIcon,
  Settings as SettingsIcon,
  ShieldCheck,
  SunIcon,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import appIconUrl from '../assets/profanity-censor-icon.svg'
import type { Capabilities, Theme } from '../types/domain'

type AppHeaderProps = {
  capabilities: Capabilities | null
  theme: Theme
  toggleTheme: () => void
}

export function AppHeader({
  capabilities,
  theme,
  toggleTheme,
}: AppHeaderProps) {
  return (
    <header className="app-header">
      <div className="brand-lockup">
        <img className="brand-mark" src={appIconUrl} alt="" />
        <div>
          <strong>Profanity Censor</strong>
          <small>Local media processing</small>
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
        <div className={`runtime-pill ${capabilities?.ready ? 'ready' : 'attention'}`}>
          {capabilities?.ready ? <ShieldCheck size={16} /> : <AlertCircle size={16} />}
          {capabilities?.ready ? 'System ready' : 'Setup required'}
        </div>
      </div>
    </header>
  )
}
