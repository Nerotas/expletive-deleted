import { ExternalLink, RefreshCw, TriangleAlert } from 'lucide-react'
import { desktopClient } from '../../services/desktop-client'

type BackendSetupPageProps = { detail?: string }

export function BackendSetupPage({ detail }: BackendSetupPageProps) {
  return <section className="page backend-setup-page" aria-labelledby="backend-setup-title">
    <TriangleAlert size={34} aria-hidden="true" />
    <p className="eyebrow">Setup required</p>
    <h1 id="backend-setup-title">Finish preparing this computer</h1>
    <p>Expletive Deleted could not start its private local processing service. This usually means Python or its required packages are not available yet. Your media has not been uploaded or changed.</p>
    {detail && <p className="backend-setup-detail">{detail}</p>}
    <ol><li>Install a supported Python version from the official Python project, if it is not already available.</li><li>Return to the app after the required local processing packages have been installed.</li><li>Choose Try again. The app will check the service and continue with the normal component walkthrough.</li></ol>
    <div className="backend-setup-actions"><button className="button secondary" onClick={() => void desktopClient.openExternal('https://www.python.org/downloads/windows/')}><ExternalLink size={16} />Open Python downloads</button><button className="button primary" onClick={() => window.location.reload()}><RefreshCw size={16} />Try again</button></div>
  </section>
}
