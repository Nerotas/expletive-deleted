import { RefreshCw, TriangleAlert } from 'lucide-react'

type BackendSetupPageProps = { detail?: string }

export function BackendSetupPage({ detail }: BackendSetupPageProps) {
  return <section className="page backend-setup-page" aria-labelledby="backend-setup-title">
    <TriangleAlert size={34} aria-hidden="true" />
    <p className="eyebrow">App repair needed</p>
    <h1 id="backend-setup-title">Repair Expletive Deleted</h1>
    <p>A component that came with Expletive Deleted could not start. Your media and settings have not changed.</p>
    {detail && <p className="backend-setup-detail">{detail}</p>}
    <ol><li>Choose Try again to restart the app’s local processing service.</li><li>If it still cannot start, reinstall Expletive Deleted.</li><li>Use diagnostics when contacting support or reporting a development issue.</li></ol>
    <div className="backend-setup-actions"><button className="button primary" onClick={() => window.location.reload()}><RefreshCw size={16} />Try again</button></div>
  </section>
}
