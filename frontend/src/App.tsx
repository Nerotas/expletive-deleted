import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AppHeader } from './components/AppHeader'
import { SetupBand } from './components/SetupBand'
import { SetupConsentDialog } from './components/SetupConsentDialog'
import type { InstallStatus } from './types/domain'
import { AlertBanner } from './components/ui/AlertBanner'
import { LoadingRow } from './components/ui/LoadingRow'
import { DictionaryPage } from './features/dictionary/DictionaryPage'
import { ReviewDialog } from './features/dictionary/ReviewDialog'
import { useDictionary } from './features/dictionary/useDictionary'
import { useCapabilities } from './features/capabilities/useCapabilities'
import { QueuePage } from './features/queue/QueuePage'
import { useQueue } from './features/queue/useQueue'
import { OnboardingPage } from './features/onboarding/OnboardingPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { useSettingsController } from './features/settings/useSettingsController'
import { useTheme } from './hooks/use-theme'
import './App.css'
import './theme.css'

function App() {
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [installDialogOpen, setInstallDialogOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()

  const reportError = useCallback((message: string) => {
    setNotice(null)
    setError(message)
  }, [])
  const reportNotice = useCallback((message: string) => {
    setError(null)
    setNotice(message)
  }, [])

  const capabilities = useCapabilities({ onError: reportError, onNotice: reportNotice })
  const settings = useSettingsController({
    onError: reportError,
    onNotice: reportNotice,
    onSaved: capabilities.refresh,
  })
  useEffect(() => {
    if (capabilities.installState && ['running', 'canceling'].includes(capabilities.installState.status)) {
      setInstallDialogOpen(true)
    }
  }, [capabilities.installState])

  const queue = useQueue({
    enabled: location.pathname === '/' && settings.persisted?.onboarding.completed === true,
    onError: reportError,
    onNotice: reportNotice,
  })
  const dictionary = useDictionary({
    enabled: location.pathname === '/dictionary' || location.pathname === '/onboarding',
    onError: reportError,
    onNotice: reportNotice,
  })

  return (
    <div className="app-shell">
      <AppHeader
        capabilities={capabilities.capabilities}
        checking={capabilities.checking}
        installState={capabilities.installState}
        theme={theme}
        toggleTheme={toggleTheme}
        onOpenInstall={() => setInstallDialogOpen(true)}
      />
      <main>
        {error && <AlertBanner tone="error" message={error} onDismiss={() => setError(null)} />}
        {notice && <AlertBanner tone="success" message={notice} onDismiss={() => setNotice(null)} />}
        {location.pathname !== '/onboarding' && !capabilities.loading && capabilities.capabilities && !capabilities.capabilities.ready && (
          <SetupBand
            capabilities={capabilities.capabilities}
            reviewInstall={(components) => void capabilities.reviewInstall(components)}
            locateExisting={(component) => void capabilities.locateExisting(component)}
            checkAgain={() => void capabilities.refresh()}
            busy={capabilities.busy}
          />
        )}

        <Routes>
          <Route
            path="/onboarding"
            element={
              settings.loading || !settings.draft
                ? <LoadingRow>Loading setup</LoadingRow>
                : (
                  <OnboardingPage
                    settings={settings}
                    capabilities={capabilities.capabilities}
                    checking={capabilities.checking}
                    capabilityBusy={capabilities.busy}
                    dictionary={dictionary}
                    onReviewInstall={(components) => void capabilities.reviewInstall(components)}
                    onLocateExisting={(component) => void capabilities.locateExisting(component)}
                    onCheckAgain={() => void capabilities.refresh()}
                    onFinished={() => navigate('/')}
                    onError={reportError}
                  />
                )
            }
          />
          <Route
            path="/"
            element={(
              settings.loading
                ? <LoadingRow>Loading settings</LoadingRow>
                : settings.persisted && !settings.persisted.onboarding.completed
                  ? <Navigate to="/onboarding" replace />
                  : (
                    <QueuePage
                      queue={queue}
                      settings={settings.persisted}
                      capabilities={capabilities.capabilities}
                      onChangeFolder={() => navigate('/settings')}
                      onReview={(source) => void dictionary.openReview(source)}
                    />
                  )
            )}
          />
          <Route
            path="/dictionary"
            element={settings.persisted && !settings.persisted.onboarding.completed
              ? <Navigate to="/onboarding" replace />
              : <DictionaryPage controller={dictionary} />}
          />
          <Route
            path="/settings"
            element={
              settings.loading
                ? <LoadingRow>Loading settings</LoadingRow>
                : settings.persisted && !settings.persisted.onboarding.completed
                  ? <Navigate to="/onboarding" replace />
                  : (
                  <SettingsPage
                    controller={settings}
                    capabilities={capabilities.capabilities}
                    checkingSystem={capabilities.busy}
                    onCheckSystem={() => void capabilities.refresh()}
                    onOpenOnboarding={() => navigate('/onboarding')}
                  />
                )
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {dictionary.review && (
        <ReviewDialog
          review={dictionary.review}
          busy={dictionary.busy}
          onClose={dictionary.closeReview}
          onClassify={(word, target) => void dictionary.updateDictionary(target, word)}
        />
      )}
      {capabilities.pendingPlan && !capabilities.installState && (
        <SetupConsentDialog
          plan={capabilities.pendingPlan}
          busy={capabilities.installing}
          onCancel={capabilities.cancelInstall}
          onContinue={() => void capabilities.approveInstall()}
        />
      )}
      {capabilities.installState && installDialogOpen && (
        <SetupProgressDialog
          installState={capabilities.installState}
          onClose={() => setInstallDialogOpen(false)}
          onCancel={() => {
            void capabilities.cancelCurrentInstall?.()
            setInstallDialogOpen(false)
          }}
        />
      )}
    </div>
  )
}

type SetupProgressDialogProps = {
  installState: InstallStatus
  onClose: () => void
  onCancel: () => void
}

function SetupProgressDialog({ installState, onClose, onCancel }: SetupProgressDialogProps) {
  const phaseLabel = (() => {
    if (installState.status === 'completed') return 'Complete'
    if (installState.phase === 'starting') return 'Preparing…'
    if (installState.phase === 'verifying') return 'Verifying…'
    if (installState.phase === 'cancelled') return 'Cancelled'
    if (installState.message.toLowerCase().includes('download')) return 'Downloading…'
    if (installState.message.toLowerCase().includes('install')) return 'Installing…'
    return 'Processing…'
  })()

  const startedAt = installState.started_at ? new Date(installState.started_at).getTime() : Date.now()
  const elapsedMs = Math.max(0, Date.now() - startedAt)
  const elapsedLabel = formatDuration(elapsedMs)

  const hasMeasurableProgress = installState.completed_bytes !== null && installState.total_bytes !== null && installState.total_bytes > 0
  const progressPercent = hasMeasurableProgress
    ? Math.min(100, Math.max(0, (installState.completed_bytes / installState.total_bytes) * 100))
    : null
  const etaSeconds = hasMeasurableProgress && progressPercent !== null && progressPercent > 0 && progressPercent < 100
    ? Math.max(0, ((installState.total_bytes - installState.completed_bytes) / Math.max(1, installState.completed_bytes / Math.max(1, elapsedMs / 1000))) / 1000)
    : null

  return (
    <div className="modal-backdrop">
      <section aria-labelledby="setup-progress-title" aria-modal="true" className="modal setup-progress" role="dialog">
        <div className="setup-progress-header">
          <span className="eyebrow">Setting things up</span>
          <button className="icon-button" type="button" aria-label="Dismiss installation progress" onClick={onClose}>×</button>
        </div>
        <h2 id="setup-progress-title">{installState.message || 'Preparing required components'}</h2>
        <p className="setup-progress-detail">{phaseLabel}</p>

        {installState.action_count && installState.action_count > 1 ? (
          <div className="setup-progress-step">Step {installState.action_index ?? 1} of {installState.action_count}</div>
        ) : null}

        {hasMeasurableProgress && progressPercent !== null ? (
          <>
            <div className="progress-bar" aria-label="Install progress">
              <span style={{ width: `${progressPercent}%` }} />
            </div>
            <div className="setup-progress-metrics">
              <strong>{formatBytes(installState.completed_bytes)} of {formatBytes(installState.total_bytes)}</strong>
              <span>{Math.round(progressPercent)}%</span>
            </div>
          </>
        ) : (
          <div className="progress-indeterminate" aria-label="Indeterminate installation progress">
            <span />
          </div>
        )}

        <div className="setup-progress-meta">
          <span>Elapsed: {elapsedLabel}</span>
          {etaSeconds !== null ? <span>Estimated remaining: {formatEta(etaSeconds)}</span> : null}
        </div>

        {installState.error ? (
          <p className="setup-progress-error">{installState.error}</p>
        ) : null}

        <div className="modal-actions setup-progress-actions">
          <button className="button secondary" type="button" onClick={onClose}>Background</button>
          <button className="button danger" type="button" onClick={onCancel}>Cancel setup</button>
        </div>
      </section>
    </div>
  )
}

function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return 'a moment'
  if (seconds < 60) return `about ${Math.max(1, Math.round(seconds))} seconds`
  const minutes = Math.round(seconds / 60)
  return `about ${minutes} minute${minutes === 1 ? '' : 's'}`
}

function formatBytes(value: number | null): string {
  if (value === null) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

export default App
