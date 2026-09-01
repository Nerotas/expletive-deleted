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
    enabled: location.pathname === '/',
    onError: reportError,
    onNotice: reportNotice,
  })
  const dictionary = useDictionary({
    enabled: location.pathname === '/dictionary',
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
        {!capabilities.loading && capabilities.capabilities && !capabilities.capabilities.ready && (
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
            path="/"
            element={(
              <QueuePage
                queue={queue}
                settings={settings.persisted}
                capabilities={capabilities.capabilities}
                onChangeFolder={() => navigate('/settings')}
                onReview={(source) => void dictionary.openReview(source)}
              />
            )}
          />
          <Route path="/dictionary" element={<DictionaryPage controller={dictionary} />} />
          <Route
            path="/settings"
            element={
              settings.loading
                ? <LoadingRow>Loading settings</LoadingRow>
                : (
                  <SettingsPage
                    controller={settings}
                    capabilities={capabilities.capabilities}
                    checkingSystem={capabilities.busy}
                    onCheckSystem={() => void capabilities.refresh()}
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
