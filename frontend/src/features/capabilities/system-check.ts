import { SYSTEM_CHECK_TIMEOUT_MS } from '../../../shared/bridge'

export { SYSTEM_CHECK_TIMEOUT_MS }

export function checkSystem<T>(read: () => Promise<T>, signal: AbortSignal): Promise<T> {
  // Bound the renderer too: an IPC acknowledgement itself can go missing.
  // Settled promises ignore late replies, so they cannot restore stale readiness.
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', abort)
    }
    const abort = () => {
      cleanup()
      reject(new DOMException('System check cancelled', 'AbortError'))
    }
    const timer = setTimeout(() => {
      cleanup()
      reject(Object.assign(new Error('The system check did not finish within 60 seconds. Retry the check. If it keeps timing out, save your edits and reopen the app.'), { code: 'request_timeout' }))
    }, SYSTEM_CHECK_TIMEOUT_MS)
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
    try {
      read().then(
        (value) => { cleanup(); resolve(value) },
        (error: unknown) => { cleanup(); reject(error) },
      )
    } catch (error) { cleanup(); reject(error) }
  })
}
