import { useCallback, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AppHeader } from './components/AppHeader'
import { SetupBand } from './components/SetupBand'
import { SetupConsentDialog } from './components/SetupConsentDialog'
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
        theme={theme}
        toggleTheme={toggleTheme}
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
      {capabilities.pendingPlan && (
        <SetupConsentDialog
          plan={capabilities.pendingPlan}
          busy={capabilities.installing}
          onCancel={capabilities.cancelInstall}
          onContinue={() => void capabilities.approveInstall()}
        />
      )}
    </div>
  )
}

export default App
