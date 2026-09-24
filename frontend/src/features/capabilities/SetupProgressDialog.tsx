import { useEffect, useRef, useState } from 'react'
import type { InstallStatus } from '../../types/domain'

import type { ConnectionState } from './installation-connection'

type SetupProgressDialogProps = {
  connection?: ConnectionState
  cancelPending?: boolean
  onRetry?: () => void
  onRestart?: () => void
  installState: InstallStatus
  onClose: () => void
  onCancel: () => void
}

export function SetupProgressDialog({ installState, onClose, onCancel, connection = { phase: 'connected', elapsedMs: 0 }, cancelPending, onRetry, onRestart }: SetupProgressDialogProps) {
  const panel = useRef<HTMLElement>(null)
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose }, [onClose])
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close.current() }
      if (event.key !== 'Tab') return
      const buttons = [...(panel.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])]
      const first = buttons[0], last = buttons.at(-1)
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previous?.focus() }
  }, [])
  const disconnected = connection.phase !== 'connected'
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const phaseLabel = (() => {
    if (installState.status === 'completed') return 'Complete'
    if (installState.phase === 'starting') return 'Preparing…'
    if (installState.phase === 'verifying') return 'Verifying…'
    if (installState.phase === 'cancelled') return 'Cancelled'
    if (installState.message.toLowerCase().includes('download')) return 'Downloading…'
    if (installState.message.toLowerCase().includes('install')) return 'Installing…'
    return 'Fetching component now…'
  })()

  const startedAt = installState.started_at ? new Date(installState.started_at).getTime() : now
  const elapsedMs = Math.max(0, now - startedAt)
  const elapsedLabel = formatDuration(elapsedMs)

  // Some setup steps do not report byte totals; keep their progress indeterminate.
  const completedBytes = installState.completed_bytes
  const totalBytes = installState.total_bytes
  const progressPercent = completedBytes !== null && totalBytes !== null && totalBytes > 0
    ? Math.min(100, Math.max(0, (completedBytes / totalBytes) * 100))
    : null
  const hasMeasurableProgress = progressPercent !== null
  const averageSpeedBytesPerSecond = (
    completedBytes !== null
    && completedBytes > 0
    && elapsedMs > 0
  )
    ? completedBytes / (elapsedMs / 1000)
    : null
  const measuredEtaSeconds = (
    completedBytes !== null
    && totalBytes !== null
    && averageSpeedBytesPerSecond !== null
    && averageSpeedBytesPerSecond > 0
    && completedBytes < totalBytes
  )
    ? Math.max(0, (totalBytes - completedBytes) / averageSpeedBytesPerSecond)
    : null
  const fallbackEtaSeconds = completedBytes !== null && totalBytes !== null && progressPercent !== null && progressPercent > 0 && progressPercent < 100
    ? Math.max(0, (totalBytes - completedBytes) / Math.max(1, completedBytes / Math.max(1, elapsedMs / 1000)))
    : null
  const etaSeconds = measuredEtaSeconds ?? fallbackEtaSeconds

  return (
    <div className="modal-backdrop">
      <section ref={panel} tabIndex={-1} aria-labelledby="setup-progress-title" aria-modal="true" className="modal setup-progress" role="dialog">
        <div className="setup-progress-header">
          <span className="eyebrow">Setting things up</span>
          <button className="icon-button" type="button" aria-label="Dismiss installation progress" onClick={onClose}>×</button>
        </div>
        <h2 id="setup-progress-title">{connection.phase === 'reconnecting' ? 'Reconnecting to setup' : connection.phase === 'recovery' ? 'Setup needs attention' : installState.message || 'Preparing required components'}</h2>
        <div role="status" aria-live="polite" aria-atomic="true">
          {connection.phase === 'reconnecting' && <p>Contact lost. Reconnecting for up to 30 seconds. Elapsed: {Math.floor(connection.elapsedMs / 1000)}s.</p>}
          {connection.phase === 'recovery' && <p>{connection.reason === 'backend_exited' ? 'The local processing service has stopped. ' : 'Unable to confirm setup status. '}The installation outcome is unknown.</p>}
          {cancelPending && !disconnected && <p>Checking whether setup has stopped.</p>}
        </div>
        {disconnected && <>
          <p>Last reported: {installState.message}. Completed downloads and verified components are retained.</p>
          <p>Retry connection checks status only. Restarting the app may stop unfinished work. Review a fresh setup plan before installing anything further.</p>
        </>}
        {!disconnected && <>
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
          {averageSpeedBytesPerSecond !== null ? <span>Download speed: {formatSpeed(averageSpeedBytesPerSecond)}</span> : null}
          {etaSeconds !== null ? <span>Estimated remaining: {formatEta(etaSeconds)}</span> : null}
        </div>

        {installState.error ? (
          <p className="setup-progress-error">{installState.error}</p>
        ) : null}

        </>}
        <div className="modal-actions setup-progress-actions">
          <button className="button secondary" type="button" onClick={onClose}>Background</button>
          {!disconnected && <button className="button danger" type="button" disabled={cancelPending || installState.status === 'canceling' || installState.status === 'resolving'} onClick={onCancel}>Cancel setup</button>}
          {connection.phase === 'recovery' && <>
            <button className="button secondary" type="button" disabled={['backend_exited', 'backend_changed', 'protocol_error'].includes(connection.reason ?? '')} onClick={onRetry}>Retry connection</button>
            <button className="button primary" type="button" onClick={onRestart}>Restart app</button>
          </>}
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

function formatSpeed(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return '0 B/s'
  return `${formatBytes(Math.round(bytesPerSecond))}/s`
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
