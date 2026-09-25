import { StringDecoder } from 'node:string_decoder'

import type { BackendState, RequestOptions } from '../shared/bridge.js'
export type { BackendState, RequestOptions } from '../shared/bridge.js'
export const transportError = (code: string, message: string) => Object.assign(new Error(message), { code })
type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void; timer?: ReturnType<typeof setTimeout> }

export class BridgeTransport {
  private nextId = 0
  private pending = new Map<number, Pending>()
  private buffer = ''
  private decoder = new StringDecoder('utf8')
  private state: BackendState
  private write: (line: string, done: (error?: Error | null) => void) => void
  private publish: (state: BackendState) => void

  constructor(generation: number, write: BridgeTransport['write'], publish: BridgeTransport['publish']) {
    this.state = { generation, status: 'running' }
    this.write = write
    this.publish = publish
  }

  get snapshot(): BackendState { return { ...this.state } }
  get pendingCount(): number { return this.pending.size }

  request(method: string, params?: Record<string, unknown>, options: RequestOptions = {}): Promise<unknown> {
    if (options.generation !== undefined && options.generation !== this.state.generation) {
      return Promise.reject(transportError('backend_changed', 'The local service has changed. Check setup again.'))
    }
    if (this.state.status !== 'running') return Promise.reject(transportError(`backend_${this.state.status}`, 'The local processing service is unavailable.'))
    const control = ['dependencies.status', 'dependencies.active', 'dependencies.install', 'dependencies.cancel'].includes(method)
    // Do not put a setup deadline on unrelated, potentially long media imports.
    const maximum = control ? 2000 : method === 'dependencies.resolve_conflict' ? 60_000 : undefined
    const timeout = Number.isFinite(options.timeoutMs) ? Math.max(1, Math.min(maximum ?? 60_000, options.timeoutMs!)) : maximum
    const id = ++this.nextId
    return new Promise((resolve, reject) => {
      const timer = timeout === undefined ? undefined : setTimeout(() => this.reject(id, transportError('request_timeout', 'The local processing service did not respond in time.')), timeout)
      this.pending.set(id, { resolve, reject, timer })
      try {
        this.write(`${JSON.stringify({ id, method, ...(params ? { params } : {}) })}\n`, (error) => {
          if (error) this.stop('unavailable')
        })
      } catch { this.stop('unavailable') }
    })
  }

  receive(chunk: Buffer): void {
    // Pipe chunks may split both JSON lines and multibyte UTF-8 characters.
    this.buffer += this.decoder.write(chunk)
    let newline: number
    while ((newline = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, newline)
      this.buffer = this.buffer.slice(newline + 1)
      let value: unknown
      try { value = JSON.parse(line) } catch {
        this.rejectAll(transportError('protocol_error', 'The local service sent an unreadable response.'))
        continue
      }
      const response = value as { id?: number; ok?: boolean; result?: unknown; error?: { message?: unknown; code?: unknown; diagnostic?: unknown } } | null
      if (!response || !Number.isSafeInteger(response.id)) {
        this.rejectAll(transportError('protocol_error', 'The local service sent an invalid response.'))
        continue
      }
      const request = this.pending.get(response.id!)
      if (!request) continue // Timed-out replies can never settle another request.
      // Validate before removing correlation so malformed replies reject their
      // waiting caller instead of leaving an unresolved promise behind.
      if (response.ok === true && Object.hasOwn(response, 'result') && !Object.hasOwn(response, 'error')) {
        this.remove(response.id!)
        request.resolve(response.result)
      } else if (response.ok === false && !Object.hasOwn(response, 'result') && response.error
        && typeof response.error.message === 'string'
        && (response.error.code == null || typeof response.error.code === 'string')
        && (response.error.diagnostic == null || typeof response.error.diagnostic === 'string')) {
        this.reject(response.id!, Object.assign(new Error(response.error.message), {
          code: response.error.code, diagnostic: response.error.diagnostic,
        }))
      } else this.reject(response.id!, transportError('protocol_error', 'The local service sent an invalid response.'))
    }
  }

  stop(status: 'exited' | 'unavailable'): void {
    if (this.state.status === 'exited') return
    this.state = { ...this.state, status }
    this.rejectAll(transportError(`backend_${status}`, 'The local processing service stopped responding.'))
    this.publish(this.snapshot)
  }

  private remove(id: number): void {
    clearTimeout(this.pending.get(id)?.timer)
    this.pending.delete(id)
  }
  private reject(id: number, error: Error): void {
    const request = this.pending.get(id)
    this.remove(id)
    request?.reject(error)
  }
  private rejectAll(error: Error): void {
    for (const id of this.pending.keys()) this.reject(id, error)
  }
}
