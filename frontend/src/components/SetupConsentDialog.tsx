import { Download, ExternalLink } from 'lucide-react'
import { desktopClient } from '../services/desktop-client'
import type { InstallPlan } from '../types/domain'
import { APPLICATION_DISPLAY_NAME } from '../constants/application'

type SetupConsentDialogProps = {
  plan: InstallPlan
  busy: boolean
  onCancel: () => void
  onContinue: () => void
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return 'Not reliably known'
  const gibibytes = bytes / (1024 ** 3)
  return `${gibibytes.toFixed(gibibytes >= 10 ? 0 : 1)} GB (approximately)`
}

export function SetupConsentDialog({
  plan,
  busy,
  onCancel,
  onContinue,
}: SetupConsentDialogProps) {
  return (
    <div className="modal-backdrop">
      <section
        aria-labelledby="setup-consent-title"
        aria-modal="true"
        className="modal setup-consent"
        role="dialog"
      >
        <span className="eyebrow">Your approval is required</span>
        <h2 id="setup-consent-title">Retrieve required components?</h2>
        <p>
          {APPLICATION_DISPLAY_NAME} needs these third-party components for local media processing.
          Continuing asks the application to retrieve and store them on this computer.
        </p>

        <div className="setup-consent-actions-list">
          {plan.actions.map((action) => (
            <article key={action.id}>
              <strong>{action.description}</strong>
              <dl>
                <div><dt>Source</dt><dd>{action.source_name}</dd></div>
                <div><dt>Stored in</dt><dd title={action.destination}>{action.destination}</dd></div>
                <div><dt>Download size</dt><dd>{formatSize(action.estimated_download_bytes)}</dd></div>
              </dl>
              <button
                className="setup-source-link"
                onClick={() => void desktopClient.openExternal(action.source_url)}
              >
                View project or provider <ExternalLink size={13} />
              </button>
            </article>
          ))}
        </div>

        <p className="setup-third-party-note">
          These projects are not developed or distributed as part of {APPLICATION_DISPLAY_NAME}.
          Canceling leaves the current setup unchanged.
        </p>
        <div className="modal-actions">
          <button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button>
          <button className="button primary" disabled={busy} onClick={onContinue}>
            <Download size={16} />{busy ? 'Working…' : 'Continue'}
          </button>
        </div>
      </section>
    </div>
  )
}
