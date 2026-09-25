import type { BackendState } from '../../../shared/bridge'
import type { DesktopClient } from '../../services/desktop-client'
import type { InstallStatus } from '../../types/domain'
import { decodeInstallStatus } from '../../services/install-status'

export const RECONNECT_WINDOW_MS = 30_000
export const STATUS_TIMEOUT_MS = 2000
export type ConnectionState = { phase: 'connected' | 'reconnecting' | 'recovery'; elapsedMs: number; reason?: string }
export type InstallTarget = { installId: string } | { planId: string }
type Client = Pick<DesktopClient, 'getBackendState' | 'onBackendState' | 'getInstallStatus' | 'getActiveInstall'>
export const errorCode = (reason: unknown) => (reason as { code?: string } | null)?.code
export const isCommunicationError = (reason: unknown) => ['request_timeout', 'backend_exited', 'backend_unavailable', 'backend_changed', 'protocol_error'].includes(errorCode(reason) ?? '')
const immediateRecovery = (reason: unknown) => ['backend_exited', 'backend_changed', 'protocol_error', 'install_unknown'].includes(errorCode(reason) ?? '')
const active = (status: InstallStatus) => ['running', 'canceling', 'resolving'].includes(status.status)

function validateStatus(value: InstallStatus | null, target: InstallTarget): InstallStatus {
  if (!value) throw Object.assign(new Error('The installation outcome is unknown.'), { code: 'install_unknown' })
  return decodeInstallStatus(value, 'installId' in target ? target.installId : undefined)
}

// One observer owns all timers and responses. Disposal invalidates even promises
// which the platform cannot abort, so old operations cannot update the screen.
export class InstallationConnection {
  private disposed = false
  private generation: number | undefined
  private epoch = 0
  private deadline: number | null = null
  private failures = 0
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private unsubscribe: (() => void) | undefined
  private client: Client
  private target: InstallTarget
  private changed: (state: ConnectionState) => void
  private received: (status: InstallStatus) => void
  private state: ConnectionState = { phase: 'connected', elapsedMs: 0 }

  constructor(client: Client, target: InstallTarget, changed: InstallationConnection['changed'], received: InstallationConnection['received']) {
    this.client = client; this.target = target; this.changed = changed; this.received = received
  }

  start(initialFailure?: unknown): void {
    this.emit({ phase: 'connected', elapsedMs: 0 })
    this.unsubscribe = this.client.onBackendState((state) => this.backendChanged(state))
    if (initialFailure) this.failure(initialFailure, false)
    if (this.state.phase === 'recovery') return
    void this.client.getBackendState().then((state) => {
      if (this.disposed || this.state.phase === 'recovery') return
      this.backendChanged(state)
      void this.poll()
    }).catch((reason) => this.failure(reason))
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true; this.epoch++
    this.clearTimers(); this.unsubscribe?.()
  }

  private later(callback: () => void, delay: number): ReturnType<typeof setTimeout> {
    const timer = setTimeout(() => { this.timers.delete(timer); callback() }, delay)
    this.timers.add(timer)
    return timer
  }
  private clearTimers(): void { for (const timer of this.timers) clearTimeout(timer); this.timers.clear() }
  private emit(state: ConnectionState): void { this.state = state; this.changed(state) }
  private elapsed(): number { return this.deadline === null ? 0 : Math.min(RECONNECT_WINDOW_MS, RECONNECT_WINDOW_MS - (this.deadline - performance.now())) }
  private recover(reason: string): void {
    if (this.disposed) return
    if (this.state.phase === 'recovery') {
      if (['backend_exited', 'backend_changed'].includes(reason)) this.emit({ ...this.state, reason })
      return
    }
    this.epoch++; this.clearTimers()
    this.emit({ phase: 'recovery', elapsedMs: this.elapsed(), reason })
  }
  private backendChanged(state: BackendState): void {
    if (this.disposed) return
    if (this.generation !== undefined && this.generation !== state.generation) {
      this.recover('backend_changed'); return
    }
    this.generation = state.generation
    if (state.status === 'exited') this.recover('backend_exited')
    else if (state.status === 'unavailable') this.failure({ code: 'backend_unavailable' }, false)
  }
  private tick = (): void => {
    if (this.disposed || this.state.phase !== 'reconnecting') return
    if (performance.now() >= this.deadline!) { this.recover('request_timeout'); return }
    this.emit({ phase: 'reconnecting', elapsedMs: this.elapsed() })
    this.later(this.tick, Math.min(250, this.deadline! - performance.now()))
  }
  private failure(reason: unknown, schedule = true): void {
    if (this.disposed || this.state.phase === 'recovery') return
    if (immediateRecovery(reason)) { this.recover(errorCode(reason)!); return }
    if (this.deadline === null) {
      this.deadline = performance.now() + RECONNECT_WINDOW_MS
      this.emit({ phase: 'reconnecting', elapsedMs: 0 })
      this.later(() => this.recover('request_timeout'), RECONNECT_WINDOW_MS)
      this.later(this.tick, 250)
    }
    const remaining = this.deadline - performance.now()
    if (remaining <= 0) { this.recover('request_timeout'); return }
    if (schedule) {
      const delay = Math.min(1000 * 2 ** Math.min(this.failures++, 3), remaining)
      this.later(() => void this.poll(), delay)
    }
  }
  private async poll(): Promise<void> {
    if (this.disposed || this.state.phase === 'recovery') return
    const epoch = ++this.epoch
    const remaining = this.deadline === null ? STATUS_TIMEOUT_MS : this.deadline - performance.now()
    if (remaining <= 0) { this.recover('request_timeout'); return }
    const timeout = Math.min(STATUS_TIMEOUT_MS, remaining)
    let timeoutTimer: ReturnType<typeof setTimeout> | undefined
    try {
      const request = 'installId' in this.target
        ? this.client.getInstallStatus(this.target.installId, timeout, this.generation)
        : this.client.getActiveInstall(this.target.planId, timeout, this.generation)
      const result = await Promise.race([request, new Promise<never>((_resolve, reject) => {
        timeoutTimer = this.later(() => reject({ code: 'request_timeout' }), timeout)
      })])
      if (this.disposed || epoch !== this.epoch) return
      if (this.deadline !== null && performance.now() >= this.deadline) { this.recover('request_timeout'); return }
      const status = validateStatus(result, this.target)
      this.target = { installId: status.install_id }
      this.clearTimers(); this.deadline = null; this.failures = 0
      this.emit({ phase: 'connected', elapsedMs: 0 })
      this.received(status)
      if (active(status)) this.later(() => void this.poll(), 1200)
      else if (status.status !== 'awaiting_resolution') this.dispose()
    } catch (reason) {
      if (!this.disposed && epoch === this.epoch) this.failure(reason)
    } finally {
      if (timeoutTimer !== undefined) { clearTimeout(timeoutTimer); this.timers.delete(timeoutTimer) }
    }
  }
}
