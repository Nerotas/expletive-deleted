import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { createQueryClient } from '../../query-client'
import { desktopClient } from '../../services/desktop-client'
import { defaultSettings } from '../../test/fixtures'
import type { SettingsSnapshot, SettingsResult } from '../../types/domain'
import { useSettingsController } from './useSettingsController'

const base: SettingsSnapshot = { settings: defaultSettings, revision: 'base' }
function saved(snapshot: SettingsSnapshot): SettingsResult { return { status: 'saved', snapshot, conflicts: [] } }
function setup() {
  const query = createQueryClient()
  const onError = vi.fn()
  const hook = renderHook(() => useSettingsController({ onError, onNotice: vi.fn(), onSaved: vi.fn() }), {
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={query}>{children}</QueryClientProvider>,
  })
  return { ...hook, query, onError }
}

describe('settings transactions controller', () => {
  beforeEach(() => {
    vi.spyOn(desktopClient, 'getSettings').mockResolvedValue(structuredClone(base))
    vi.spyOn(desktopClient, 'updateSettings').mockImplementation(async (settings) => saved({ settings, revision: 'saved' }))
    vi.spyOn(desktopClient, 'patchSettings').mockResolvedValue(saved(base))
  })

  it('keeps a dirty draft and its baseline when component settings refresh', async () => {
    const { result, query } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    act(() => result.current.updateGroup('censoring', { ...defaultSettings.censoring, padding_before_ms: 333 }))
    const newer = structuredClone(base)
    newer.revision = 'component'
    newer.settings.runtime.whisper_cache = 'C:\\verified'
    act(() => query.setQueryData(['settings'], newer))
    expect(result.current.draft?.censoring.padding_before_ms).toBe(333)
    await act(() => result.current.save())
    expect(desktopClient.updateSettings).toHaveBeenCalledWith(expect.objectContaining({ censoring: expect.objectContaining({ padding_before_ms: 333 }) }), base)
  })

  it('retains edits made during a pending save and rejects duplicate saves', async () => {
    let finish!: (value: SettingsResult) => void
    vi.mocked(desktopClient.updateSettings).mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    const { result } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    act(() => result.current.updateGroup('censoring', { ...defaultSettings.censoring, padding_before_ms: 333 }))
    let pending!: Promise<void>
    act(() => { pending = result.current.save() })
    act(() => result.current.updateGroup('censoring', { ...defaultSettings.censoring, padding_before_ms: 444 }))
    await act(() => result.current.save())
    expect(desktopClient.updateSettings).toHaveBeenCalledTimes(1)
    const submitted = vi.mocked(desktopClient.updateSettings).mock.calls[0][0]
    await act(async () => { finish(saved({ settings: submitted, revision: 'saved' })); await pending })
    expect(result.current.draft?.censoring.padding_before_ms).toBe(444)
    expect(result.current.dirty).toBe(true)
    act(() => result.current.discard())
    expect(result.current.draft?.censoring.padding_before_ms).toBe(333)
  })

  it.each([true, false])('resolves a conflict with explicit draft choice %s and a fresh revision', async (useDraft) => {
    const latest = structuredClone(base)
    latest.revision = 'new'
    latest.settings.censoring.padding_before_ms = 222
    const conflict: SettingsResult = { status: 'conflict', snapshot: latest, conflicts: [{ field: 'censoring.padding_before_ms', expected: 100, current: 222, proposed: 333 }] }
    vi.mocked(desktopClient.updateSettings).mockResolvedValue(conflict)
    const { result } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    act(() => result.current.updateGroup('censoring', { ...defaultSettings.censoring, padding_before_ms: 333 }))
    let pending!: Promise<void>
    act(() => { pending = result.current.save() })
    await waitFor(() => expect(result.current.conflict).toEqual(conflict))
    await act(async () => { result.current.resolveConflict({ 'censoring.padding_before_ms': useDraft }); await pending })
    expect(desktopClient.patchSettings).toHaveBeenCalledWith('new', [{ field: 'censoring.padding_before_ms', expected: 222, value: useDraft ? 333 : 222 }], true)
  })

  it('retains a wizard draft on cancellation and does not report a successful save', async () => {
    vi.mocked(desktopClient.patchSettings).mockResolvedValue({ status: 'conflict', snapshot: base, conflicts: [] })
    const { result } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    const draft = structuredClone(base.settings)
    draft.onboarding.last_step = 'components'
    let pending!: Promise<SettingsSnapshot | null>
    act(() => { pending = result.current.saveDraft(draft, base) })
    await waitFor(() => expect(result.current.conflict).not.toBeNull())
    await act(async () => { result.current.cancelConflict(); expect(await pending).toBeNull() })
    expect(draft.onboarding.last_step).toBe('components')
    expect(desktopClient.patchSettings).toHaveBeenCalledTimes(1)
  })

  it('requires a new choice when resolution conflicts again', async () => {
    const conflict: SettingsResult = { status: 'conflict', snapshot: { ...base, revision: 'new' }, conflicts: [{ field: 'censoring.padding_before_ms', expected: 100, current: 100, proposed: 333 }] }
    vi.mocked(desktopClient.updateSettings).mockResolvedValue(conflict)
    vi.mocked(desktopClient.patchSettings).mockResolvedValue({ ...conflict, snapshot: { ...base, revision: 'newer' } })
    const { result } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    act(() => result.current.updateGroup('censoring', { ...defaultSettings.censoring, padding_before_ms: 333 }))
    let pending!: Promise<void>
    act(() => { pending = result.current.save() })
    await waitFor(() => expect(result.current.conflict?.snapshot.revision).toBe('new'))
    act(() => result.current.resolveConflict({ 'censoring.padding_before_ms': true }))
    await waitFor(() => expect(result.current.conflict?.snapshot.revision).toBe('newer'))
    expect(result.current.draft?.censoring.padding_before_ms).toBe(333)
    await act(async () => { result.current.cancelConflict(); await pending })
  })

  it('discards to the latest persisted snapshot after cancelling a conflict', async () => {
    const latest = structuredClone(base)
    latest.revision = 'latest'
    latest.settings.censoring.padding_before_ms = 222
    vi.mocked(desktopClient.updateSettings).mockResolvedValue({ status: 'conflict', snapshot: latest, conflicts: [{ field: 'censoring.padding_before_ms', expected: 100, current: 222, proposed: 333 }] })
    const { result } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    act(() => result.current.updateGroup('censoring', { ...defaultSettings.censoring, padding_before_ms: 333 }))
    let pending!: Promise<void>
    act(() => { pending = result.current.save() })
    await waitFor(() => expect(result.current.conflict).not.toBeNull())
    await act(async () => { result.current.cancelConflict(); await pending })
    expect(result.current.draft?.censoring.padding_before_ms).toBe(333)
    act(() => result.current.discard())
    expect(result.current.draft?.censoring.padding_before_ms).toBe(222)
  })

  it('keeps failed edits and reports persistence errors', async () => {
    vi.mocked(desktopClient.updateSettings).mockRejectedValue(new Error('Disk full'))
    const { result, onError } = setup()
    await waitFor(() => expect(result.current.draft).not.toBeNull())
    act(() => result.current.updateGroup('processing', { ...defaultSettings.processing, device: 'cpu' }))
    await act(() => result.current.save())
    expect(result.current.draft?.processing.device).toBe('cpu')
    expect(result.current.dirty).toBe(true)
    expect(onError).toHaveBeenCalledWith('Disk full')
  })
})
