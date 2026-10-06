// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import { loadSecurityDocument } from './security-navigation.mjs'

describe('security fixture navigation', () => {
  it('adopts the new document after Electron finishes loading instead of observing old navigation failures', async () => {
    let finish!: () => void
    const load = vi.fn(() => new Promise<void>((resolve) => { finish = resolve }))
    const ready = vi.fn(async () => undefined)
    const result = loadSecurityDocument(load, ready)
    expect(ready).not.toHaveBeenCalled()
    finish()
    await result
    expect(ready).toHaveBeenCalledOnce()
  })
  it('recovers socket exhaustion, then still requires successful document readiness', async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error('net::ERR_NO_BUFFER_SPACE')).mockResolvedValueOnce(undefined)
    const ready = vi.fn(async () => undefined)
    const pause = vi.fn(async () => undefined), onRetry = vi.fn()
    await loadSecurityDocument(load, ready, { pause, onRetry })
    expect(load).toHaveBeenCalledTimes(2)
    expect(ready).toHaveBeenCalledOnce()
    expect(pause).toHaveBeenCalledWith(100)
    expect(onRetry).toHaveBeenCalledWith(1)
  })
  it('fails persistent buffer exhaustion after three attempts', async () => {
    const error = new Error('net::ERR_NO_BUFFER_SPACE')
    const load = vi.fn(async () => { throw error })
    const ready = vi.fn(), pause = vi.fn(async () => undefined), onRetry = vi.fn()
    await expect(loadSecurityDocument(load, ready, { pause, onRetry })).rejects.toBe(error)
    expect(load).toHaveBeenCalledTimes(3)
    expect(ready).not.toHaveBeenCalled()
    expect(pause.mock.calls).toEqual([[100], [200]])
  })
  it.each(['ERR_FAILED', 'ERR_ABORTED', 'ERR_BLOCKED_BY_CLIENT', 'Wrong foreign document', 'Timeout 15000ms exceeded'])('never retries or hides %s', async (message) => {
    const error = new Error(message)
    const load = vi.fn(async () => undefined)
    const ready = vi.fn(async () => { throw error })
    const pause = vi.fn(), onRetry = vi.fn()
    await expect(loadSecurityDocument(load, ready, { pause, onRetry })).rejects.toBe(error)
    expect(load).toHaveBeenCalledOnce()
    expect(onRetry).not.toHaveBeenCalled()
    expect(pause).not.toHaveBeenCalled()
  })
})
