import { ExternalLink, RefreshCw, TriangleAlert } from 'lucide-react'
import { desktopClient } from '../../services/desktop-client'

type BackendSetupPageProps = {
  detail?: string
  pythonRequired?: boolean
}

export function BackendSetupPage({ detail, pythonRequired = false }: BackendSetupPageProps) {
  const title = pythonRequired ? 'Install Python to continue' : 'Finish preparing this computer'
  return <section className="page backend-setup-page" aria-labelledby="backend-setup-title">
    <TriangleAlert size={34} aria-hidden="true" />
    <p className="eyebrow">Setup required</p>
    <h1 id="backend-setup-title">{title}</h1>
    <p>{pythonRequired
      ? 'Expletive Deleted needs a supported Python installation to process media locally. Your media has not been uploaded or changed.'
      : 'Expletive Deleted could not start its private local processing service. This usually means Python or its required packages are not available yet. Your media has not been uploaded or changed.'}
    </p>
    {detail && <p className="backend-setup-detail">{detail}</p>}
    <ol><li>Choose Get Python to open the official Python download page.</li><li>Install a supported Python version, then return here.</li><li>Choose Try again. The app will check the service and continue with the normal component walkthrough.</li></ol>
    <div className="backend-setup-actions"><button className="button secondary" onClick={() => void desktopClient.openExternal('https://www.python.org/downloads/windows/')}><ExternalLink size={16} />Get Python</button><button className="button primary" onClick={() => window.location.reload()}><RefreshCw size={16} />Try again</button></div>
  </section>
}
