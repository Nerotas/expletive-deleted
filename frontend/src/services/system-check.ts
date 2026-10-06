import type { Capabilities, SystemCheck } from '../types/domain'

const STAGES = ['starting', 'waiting_previous_check', 'media_tools', 'ffmpeg', 'ffprobe', 'python_packages', 'speech_model', 'ytdlp', 'js_runtime', 'device', 'encoders']
const object = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value))
const duration = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value >= 0

export function decodeSystemCheck(value: unknown): SystemCheck {
  if (!object(value) || typeof value.check_id !== 'string' || !value.check_id || value.check_id.length > 64
    || !['running', 'completed', 'failed'].includes(String(value.status)) || !STAGES.includes(String(value.stage))
    || !duration(value.elapsed_ms) || !duration(value.stage_elapsed_ms) || !object(value.timings)
    || Object.keys(value.timings).length > 9 || !Object.entries(value.timings).every(([stage, ms]) => STAGES.slice(2).includes(stage) && duration(ms))
    || (value.error !== null && typeof value.error !== 'string')
    || (value.status === 'completed'
      ? !object(value.capabilities) || typeof value.capabilities.ready !== 'boolean' || typeof value.capabilities.processing_ready !== 'boolean'
      : value.capabilities !== null)) {
    throw Object.assign(new Error('The local service sent an invalid verification status.'), { code: 'protocol_error' })
  }
  return value as SystemCheck
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(new DOMException('Verification observer cancelled', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, ms)
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
  })
}

async function readStatus(read: () => Promise<unknown>, signal: AbortSignal): Promise<SystemCheck> {
  // Only the lightweight acknowledgement has a deadline. The actual verifier
  // keeps running, so reconnecting can recover its eventual result.
  return new Promise((resolve, reject) => {
    const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', abort) }
    const abort = () => { cleanup(); reject(new DOMException('Verification observer cancelled', 'AbortError')) }
    const timer = setTimeout(() => {
      cleanup()
      reject(Object.assign(new Error('Contact with system verification was interrupted. Reconnect to check its progress.'), { code: 'request_timeout' }))
    }, 2000)
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
    try {
      read().then((value) => {
        try { resolve(decodeSystemCheck(value)) } catch (error) { reject(error) }
        finally { cleanup() }
      }, (error: unknown) => { cleanup(); reject(error) })
    } catch (error) { cleanup(); reject(error) }
  })
}

export async function observeSystemCheck(start: () => Promise<unknown>, status: () => Promise<unknown>,
  onProgress?: (state: SystemCheck) => void, signal = new AbortController().signal, startupDelayMs = 0): Promise<Capabilities> {
  // Startup grace is cancellable and precedes the acknowledgement deadline.
  if (startupDelayMs > 0) await wait(startupDelayMs, signal)
  let current = await readStatus(start, signal)
  while (!signal.aborted) {
    onProgress?.(current)
    if (current.status === 'completed') return current.capabilities!
    if (current.status === 'failed') throw new Error(current.error || 'System verification could not complete. Retry the check.')
    await wait(1000, signal)
    current = await readStatus(status, signal)
  }
  throw new DOMException('Verification observer cancelled', 'AbortError')
}
