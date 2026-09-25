import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useInstallStatus, type Observation } from './useInstallStatus'
import { useCapabilities } from './useCapabilities'
import { fixture, running } from '../../test/install-fixtures'
import { desktopClient } from '../../services/desktop-client'
import { readyCapabilities } from '../../test/fixtures'

describe('setup observers and mutation reconciliation', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] }))
  afterEach(() => vi.useRealTimers())
  it('cleans up on operation changes, rejects old replies, and unsubscribes on unmount', async () => {
    const f = fixture()
    let old!: (value: typeof running) => void
    f.client.getInstallStatus.mockImplementationOnce(() => new Promise((resolve) => { old = resolve }))
    const initial: Observation = { target: { installId: 'one' } }
    const received = vi.fn()
    const hook = renderHook(({ observation }) => useInstallStatus(f.client, observation, received), { initialProps: { observation: initial } })
    await act(() => vi.advanceTimersByTimeAsync(0))
    f.client.getInstallStatus.mockResolvedValue({ ...running, install_id: 'two' })
    hook.rerender({ observation: { target: { installId: 'two' } } })
    await act(() => vi.advanceTimersByTimeAsync(0))
    await act(async () => { old(running) })
    expect(received).toHaveBeenCalledTimes(1)
    expect(received).toHaveBeenCalledWith(expect.objectContaining({ install_id: 'two' }))
    hook.unmount()
    expect(f.unsubscribe).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })
  function capabilities() {
    const f = fixture()
    const client = { ...desktopClient, ...f.client,
      getCapabilities: vi.fn(async () => readyCapabilities),
      planDependencies: vi.fn(async () => ({ plan_id: 'approved', actions: [] })),
      installDependencies: vi.fn(async () => running),
      cancelInstall: vi.fn(async () => ({ ...running, status: 'canceling' as const })),
    }
    const cache = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
    const onNotice = vi.fn(), onError = vi.fn()
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={cache}>{children}</QueryClientProvider>
    const hook = renderHook(() => useCapabilities({ client, onNotice, onError }), { wrapper })
    return { ...f, client, hook, onNotice, onError, cache }
  }
  async function approve(f: ReturnType<typeof capabilities>) {
    await act(async () => { await f.hook.result.current.reviewInstall(['whisper_model']) })
    await act(async () => { await f.hook.result.current.approveInstall() })
    await act(() => vi.advanceTimersByTimeAsync(0))
  }
  it('reconciles a lost start acknowledgement by approved token without installing twice', async () => {
    const f = capabilities()
    f.client.installDependencies.mockRejectedValue({ code: 'request_timeout' })
    await approve(f)
    expect(f.client.getActiveInstall).toHaveBeenCalledWith('approved', 2000, 1)
    expect(f.hook.result.current.installState?.install_id).toBe('one')
    await act(async () => { await f.hook.result.current.approveInstall() })
    expect(f.client.installDependencies).toHaveBeenCalledOnce()
    f.hook.unmount(); f.cache.clear()
  })
  it('keeps cancellation unknown after a lost acknowledgement and refreshes completion once', async () => {
    const f = capabilities()
    await approve(f)
    f.client.cancelInstall.mockRejectedValue({ code: 'request_timeout' })
    f.client.getInstallStatus.mockRejectedValue({ code: 'request_timeout' })
    await act(async () => { await f.hook.result.current.cancelCurrentInstall() })
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(f.hook.result.current.connection.phase).toBe('reconnecting')
    expect(f.hook.result.current.installState?.status).toBe('running')
    expect(f.onNotice).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(f.hook.result.current.connection.phase).toBe('recovery')
    f.client.getInstallStatus.mockResolvedValue({ ...running, status: 'completed' })
    await act(async () => f.hook.result.current.retryConnection())
    await act(() => vi.advanceTimersByTimeAsync(100))
    expect(f.client.cancelInstall).toHaveBeenCalledOnce()
    expect(f.client.installDependencies).toHaveBeenCalledOnce()
    expect(f.onNotice).toHaveBeenCalledExactlyOnceWith('Installation complete and verified')
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(f.onNotice).toHaveBeenCalledOnce()
    f.hook.unmount(); f.cache.clear()
  })
})
