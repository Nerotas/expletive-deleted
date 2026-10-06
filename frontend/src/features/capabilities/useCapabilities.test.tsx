import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { desktopClient } from '../../services/desktop-client'
import { readyCapabilities } from '../../test/fixtures'
import type { SystemCheck } from '../../types/domain'
import { useCapabilities } from './useCapabilities'

const running: SystemCheck = { check_id: 'one', status: 'running', stage: 'python_packages', elapsed_ms: 61000,
  stage_elapsed_ms: 61000, timings: {}, capabilities: null, error: null }

describe('background verification', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'performance'] }))
  afterEach(() => vi.useRealTimers())
  function setup(read: typeof desktopClient.getCapabilities = () => new Promise(() => {})) {
    const getCapabilities = vi.fn(read)
    const client = { ...desktopClient, getCapabilities }
    const cache = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={cache}>{children}</QueryClientProvider>
    const hook = renderHook(() => useCapabilities({ client, onError: vi.fn(), onNotice: vi.fn() }), { wrapper })
    const flush = () => act(() => vi.advanceTimersByTimeAsync(1))
    const close = () => { hook.unmount(); cache.clear() }
    return { getCapabilities, cache, hook, flush, close }
  }
  it('keeps a slow check alive without blocking setup and accepts its eventual success', async () => {
    let finish!: (value: typeof readyCapabilities) => void
    const f = setup((progress) => { progress?.(running); return new Promise((resolve) => { finish = resolve }) })
    await f.flush()
    await act(() => vi.advanceTimersByTimeAsync(75000))
    expect(f.hook.result.current.checking).toBe(true)
    expect(f.hook.result.current.busy).toBe(false)
    expect(f.hook.result.current.capabilities).toBeNull()
    expect(f.hook.result.current.checkError).toBeNull()
    expect(f.hook.result.current.checkState?.stage).toBe('python_packages')
    expect(f.getCapabilities).toHaveBeenCalledOnce()
    await act(async () => { finish(readyCapabilities) })
    await f.flush()
    expect(f.hook.result.current.capabilities?.ready).toBe(true)
    f.close()
  })
  it('reconnects without requesting another probe after contact is lost', async () => {
    const f = setup(() => Promise.reject(new Error('Contact interrupted')))
    await f.flush()
    expect(f.hook.result.current.checkError).toBe('Contact interrupted')
    f.getCapabilities.mockResolvedValueOnce(readyCapabilities)
    await act(async () => { await f.hook.result.current.reconnectCheck() })
    await f.flush()
    expect(f.getCapabilities.mock.calls[1][2]).toBe(false)
    expect(f.hook.result.current.capabilities?.ready).toBe(true)
    f.close()
  })
  it('rejects an obsolete response and progress after a fresh settings check', async () => {
    let finish!: (value: typeof readyCapabilities) => void
    let obsoleteProgress: Parameters<typeof desktopClient.getCapabilities>[0]
    const f = setup((progress) => { obsoleteProgress = progress; return new Promise((resolve) => { finish = resolve }) })
    await f.flush()
    f.getCapabilities.mockImplementationOnce(async (progress) => {
      progress?.({ ...running, check_id: 'two', elapsed_ms: 0 })
      return { ...readyCapabilities, ready: false, processing_ready: false }
    })
    await act(async () => { await f.hook.result.current.refresh() })
    await f.flush()
    await act(async () => { obsoleteProgress?.(running); finish(readyCapabilities) })
    await f.flush()
    expect(f.hook.result.current.checkState?.check_id).toBe('two')
    expect(f.hook.result.current.capabilities?.ready).toBe(false)
    expect(f.getCapabilities.mock.calls[1][2]).toBe(true)
    f.close()
  })
  it('gates processing while a previously successful result is being rechecked', async () => {
    const f = setup(() => Promise.resolve(readyCapabilities))
    await f.flush()
    expect(f.hook.result.current.capabilities?.ready).toBe(true)
    let finish!: (value: typeof readyCapabilities) => void
    f.getCapabilities.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    let refreshing!: Promise<void>
    await act(async () => { refreshing = f.hook.result.current.refresh() })
    await f.flush()
    expect(f.hook.result.current.capabilities).toBeNull()
    expect(f.hook.result.current.busy).toBe(false)
    await act(async () => { finish(readyCapabilities); await refreshing })
    f.close()
  })
})
