import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { desktopClient } from '../../services/desktop-client'
import { readyCapabilities } from '../../test/fixtures'
import { useCapabilities } from './useCapabilities'
import { SYSTEM_CHECK_TIMEOUT_MS } from './system-check'

describe('system check recovery', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'performance'] }))
  afterEach(() => vi.useRealTimers())
  function setup(read: () => Promise<typeof readyCapabilities> = () => new Promise(() => {})) {
    const getCapabilities = vi.fn(read)
    const client = { ...desktopClient, getCapabilities }
    const cache = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={cache}>{children}</QueryClientProvider>
    const hook = renderHook(() => useCapabilities({ client, onError: vi.fn(), onNotice: vi.fn() }), { wrapper })
    // Query notifications run on the next timer tick after a promise settles.
    const flush = () => act(() => vi.advanceTimersByTimeAsync(1))
    const close = () => { hook.unmount(); cache.clear() }
    return { getCapabilities, cache, hook, flush, close }
  }
  it('unblocks setup at the deadline and waits for explicit retry', async () => {
    const f = setup()
    await f.flush()
    expect(f.hook.result.current.checking).toBe(true)
    await act(() => vi.advanceTimersByTimeAsync(SYSTEM_CHECK_TIMEOUT_MS))
    await f.flush()
    expect(f.hook.result.current.checking).toBe(false)
    expect(f.hook.result.current.busy).toBe(false)
    expect(f.hook.result.current.capabilities).toBeNull()
    expect(f.hook.result.current.checkError).toContain('60 seconds')
    await act(() => vi.advanceTimersByTimeAsync(15_000))
    expect(f.getCapabilities).toHaveBeenCalledOnce()
    f.getCapabilities.mockResolvedValueOnce(readyCapabilities)
    await act(async () => { await f.hook.result.current.refresh() })
    await f.flush()
    expect(f.hook.result.current.checkError).toBeNull()
    expect(f.hook.result.current.capabilities?.ready).toBe(true)
    expect(f.getCapabilities).toHaveBeenCalledTimes(2)
    f.close()
    await f.flush()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('ignores a timed-out response after a retry has returned different results', async () => {
    let late!: (value: typeof readyCapabilities) => void
    const f = setup(() => new Promise((resolve) => { late = resolve }))
    await f.flush()
    await act(() => vi.advanceTimersByTimeAsync(SYSTEM_CHECK_TIMEOUT_MS))
    await f.flush()
    f.getCapabilities.mockResolvedValueOnce({ ...readyCapabilities, ready: false, processing_ready: false })
    await act(async () => { await f.hook.result.current.refresh() })
    await f.flush()
    await act(async () => { late(readyCapabilities) })
    await f.flush()
    expect(f.hook.result.current.capabilities?.ready).toBe(false)
    f.close()
  })
  it('removes previously verified readiness when a recheck fails', async () => {
    const f = setup(() => Promise.resolve(readyCapabilities))
    await f.flush()
    expect(f.hook.result.current.capabilities?.ready).toBe(true)
    f.getCapabilities.mockRejectedValueOnce(new Error('Service unavailable'))
    await act(async () => { await f.hook.result.current.refresh() })
    await f.flush()
    expect(f.hook.result.current.capabilities).toBeNull()
    expect(f.hook.result.current.checkError).toBe('Service unavailable')
    f.close()
  })
  it('cleans up an unfinished check when the query is cancelled', async () => {
    const f = setup()
    await f.flush()
    await act(async () => { await f.cache.cancelQueries({ queryKey: ['capabilities'] }) })
    f.close()
    await f.flush()
    expect(vi.getTimerCount()).toBe(0)
  })
})
