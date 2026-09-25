import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createQueryClient } from '../../query-client'
import { desktopClient } from '../../services/desktop-client'
import { defaultSettings, readyCapabilities } from '../../test/fixtures'
import type { SettingsResult, SettingsSnapshot } from '../../types/domain'
import { useSettingsController } from '../settings/useSettingsController'
import { applySettingChanges } from '../settings/settings-transactions'
import { SettingsConflictDialog } from '../settings/SettingsConflictDialog'
import { useDictionary } from '../dictionary/useDictionary'
import { useQueue } from '../queue/useQueue'
import { OnboardingPage } from './OnboardingPage'

describe('onboarding settings transactions', () => {
  let persisted: SettingsSnapshot
  const onError = vi.fn(), onNotice = vi.fn(), onSaved = vi.fn(), onFinished = vi.fn()
  beforeEach(() => {
    persisted = { settings: structuredClone(defaultSettings), revision: 'base' }
    persisted.settings.onboarding = { completed: false, last_step: 'settings' }
    vi.spyOn(desktopClient, 'getSettings').mockImplementation(async () => structuredClone(persisted))
    vi.spyOn(desktopClient, 'updateSettings')
    vi.spyOn(desktopClient, 'patchSettings').mockImplementation(async (_revision, changes) => {
      persisted = { settings: applySettingChanges(persisted.settings, changes), revision: `${persisted.revision}+` }
      return { status: 'saved', snapshot: structuredClone(persisted), conflicts: [] }
    })
    vi.spyOn(desktopClient, 'selectDirectory').mockResolvedValue(undefined)
  })
  function setup() {
    const query = createQueryClient()
    function Harness() {
      const settings = useSettingsController({ onError, onNotice, onSaved })
      const dictionary = useDictionary({ enabled: false, onError, onNotice })
      const queue = useQueue({ enabled: false, onError, onNotice })
      return <>
        {settings.draft && <OnboardingPage settings={settings} capabilities={readyCapabilities} checking={false} capabilityBusy={false}
          dictionary={dictionary} queue={queue} onReviewInstall={vi.fn()} onLocateExisting={vi.fn()} onCheckAgain={vi.fn()} onError={onError} onFinished={onFinished} />}
        {settings.conflict && <SettingsConflictDialog revision={settings.conflict.snapshot.revision} conflicts={settings.conflict.conflicts}
          returnFocusTo={settings.conflictFocusTarget}
          busy={settings.busy} onCancel={settings.cancelConflict} onResolve={settings.resolveConflict} />}
      </>
    }
    const rendered = render(<QueryClientProvider client={query}><MemoryRouter><Harness /></MemoryRouter></QueryClientProvider>)
    return { ...rendered, query, user: userEvent.setup() }
  }
  async function prepare(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole('button', { name: /^Keep my current dictionary/ }))
  }
  function conflict(currentInput: string): SettingsResult {
    persisted = structuredClone(persisted)
    persisted.revision += '+'
    persisted.settings.directories.input = currentInput
    return { status: 'conflict', snapshot: structuredClone(persisted), conflicts: [{ field: 'directories.input', expected: defaultSettings.directories.input, current: currentInput, proposed: 'C:/wizard-input' }] }
  }
  async function editInput(user: ReturnType<typeof userEvent.setup>) {
    const input = screen.getByRole('textbox', { name: 'Ready / Input' })
    await user.clear(input); await user.type(input, 'C:/wizard-input')
  }

  it('keeps its draft and step during background setup, sending only wizard intent', async () => {
    const { user, query } = setup()
    await prepare(user)
    await user.click(screen.getByRole('button', { name: 'Karaoke' }))
    persisted.settings.runtime.whisper_cache = 'C:/verified-model'
    persisted.settings.censoring.padding_before_ms = 375
    persisted.settings.processing.device = 'cpu'
    // The other writer already saved our eventual next step; the transaction
    // can accept that identical proposal, but the query must not move this UI.
    persisted.settings.onboarding.last_step = 'add-media'
    persisted.revision = 'background'
    act(() => query.setQueryData(['settings'], structuredClone(persisted)))
    expect(screen.getByRole('heading', { name: 'Choose your settings' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save & Continue' }))
    await screen.findByRole('heading', { name: 'Add a first file' })
    expect(desktopClient.patchSettings).toHaveBeenCalledWith('base', [
      { field: 'censoring.stereo_method', expected: 'drop_audio', value: 'karaoke' },
      { field: 'onboarding.last_step', expected: 'settings', value: 'add-media' },
    ])
    expect(desktopClient.updateSettings).not.toHaveBeenCalled()
    expect(persisted.settings.runtime.whisper_cache).toBe('C:/verified-model')
    expect(persisted.settings.censoring.padding_before_ms).toBe(375)
    expect(persisted.settings.processing.device).toBe('cpu')
    await user.click(screen.getByRole('button', { name: 'Save & Continue' }))
    expect(vi.mocked(desktopClient.patchSettings).mock.calls[1][0]).toBe('background+')
  })

  it.each([true, false])('pauses on conflict, keeps the draft on cancel, then applies explicit choice %s', async (useDraft) => {
    const { user } = setup()
    await prepare(user); await editInput(user)
    const result = conflict('C:/current-input')
    vi.mocked(desktopClient.patchSettings).mockResolvedValueOnce(result).mockResolvedValueOnce(result)
    const save = screen.getByRole('button', { name: 'Save & Continue' })
    await user.click(save)
    await screen.findByRole('dialog')
    expect(screen.getByRole('heading', { name: 'Choose your settings' })).toBeInTheDocument()
    expect(persisted.settings.onboarding.last_step).toBe('settings')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Ready / Input' })).toHaveValue('C:/wizard-input')
    expect(save).toHaveFocus()
    await user.click(save)
    await user.click(await screen.findByRole('radio', { name: useDraft ? /Use my edit/ : /Keep current/ }))
    await user.click(screen.getByRole('button', { name: 'Apply choices' }))
    await screen.findByRole('heading', { name: 'Add a first file' })
    expect(persisted.settings.directories.input).toBe(useDraft ? 'C:/wizard-input' : 'C:/current-input')
    expect(vi.mocked(desktopClient.patchSettings).mock.calls[2]).toEqual([result.snapshot.revision, [
      { field: 'directories.input', expected: 'C:/current-input', value: useDraft ? 'C:/wizard-input' : 'C:/current-input' },
      { field: 'onboarding.last_step', expected: 'settings', value: 'add-media' },
    ], true])
  })

  it('requires another choice after a concurrent change and restores original focus on cancellation', async () => {
    const { user } = setup()
    await prepare(user); await editInput(user)
    const first = conflict('C:/first-current')
    const second = conflict('C:/second-current')
    vi.mocked(desktopClient.patchSettings).mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const save = screen.getByRole('button', { name: 'Save & Continue' })
    await user.click(save)
    await user.click(await screen.findByRole('radio', { name: /Use my edit/ }))
    await user.click(screen.getByRole('button', { name: 'Apply choices' }))
    await screen.findByRole('radio', { name: /second-current/ })
    expect(screen.getByRole('button', { name: 'Apply choices' })).toBeDisabled()
    expect(persisted.settings.onboarding.last_step).toBe('settings')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(save).toHaveFocus())
    expect(screen.getByRole('textbox', { name: 'Ready / Input' })).toHaveValue('C:/wizard-input')
  })

  it.each([true, false])('uses the resolved saved step when progress itself conflicts: use draft %s', async (useDraft) => {
    const { user } = setup()
    await prepare(user)
    persisted.settings.onboarding.last_step = 'components'
    persisted.revision = 'other-progress'
    vi.mocked(desktopClient.patchSettings).mockResolvedValueOnce({ status: 'conflict', snapshot: structuredClone(persisted), conflicts: [
      { field: 'onboarding.last_step', expected: 'settings', current: 'components', proposed: 'add-media' },
    ] })
    await user.click(screen.getByRole('button', { name: 'Save & Continue' }))
    await user.click(await screen.findByRole('radio', { name: useDraft ? /Use my edit/ : /Keep current/ }))
    await user.click(screen.getByRole('button', { name: 'Apply choices' }))
    await screen.findByRole('heading', { name: useDraft ? 'Add a first file' : 'Prepare this computer' })
    expect(persisted.settings.onboarding.last_step).toBe(useDraft ? 'add-media' : 'components')
  })

  it('retains edits after a failed save and suppresses double clicks until the one request settles', async () => {
    const { user } = setup()
    await prepare(user); await editInput(user)
    let reject!: (reason: Error) => void
    vi.mocked(desktopClient.patchSettings).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
    const save = screen.getByRole('button', { name: 'Save & Continue' })
    fireEvent.click(save); fireEvent.click(save)
    expect(desktopClient.patchSettings).toHaveBeenCalledOnce()
    expect(save).toBeDisabled()
    await act(async () => reject(new Error('Disk full')))
    await waitFor(() => expect(save).toBeEnabled())
    expect(onError).toHaveBeenCalledWith('Disk full')
    expect(screen.getByRole('textbox', { name: 'Ready / Input' })).toHaveValue('C:/wizard-input')
    await user.click(save)
    await screen.findByRole('heading', { name: 'Add a first file' })
    expect(vi.mocked(desktopClient.patchSettings).mock.calls[1][0]).toBe('base')
  })

  it('retains a late picker edit through an older save response and uses the new baseline on retry', async () => {
    const { user } = setup()
    await prepare(user)
    let select!: (path: string) => void
    let finish!: (result: SettingsResult) => void
    vi.mocked(desktopClient.selectDirectory).mockImplementationOnce(() => new Promise((resolve) => { select = resolve }))
    vi.mocked(desktopClient.patchSettings).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    await user.click(screen.getByRole('button', { name: 'Choose Ready / Input' }))
    await user.click(screen.getByRole('button', { name: 'Save & Continue' }))
    await act(async () => select('C:/late-choice'))
    const saved = structuredClone(persisted)
    saved.revision = 'saved'; saved.settings.onboarding.last_step = 'add-media'
    await act(async () => finish({ status: 'saved', snapshot: saved, conflicts: [] }))
    expect(screen.getByRole('heading', { name: 'Choose your settings' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ready / Input' })).toHaveValue('C:/late-choice')
    await user.click(screen.getByRole('button', { name: 'Save & Continue' }))
    expect(vi.mocked(desktopClient.patchSettings).mock.calls[1]).toEqual(['saved', [
      { field: 'directories.input', expected: defaultSettings.directories.input, value: 'C:/late-choice' },
      { field: 'onboarding.last_step', expected: 'add-media', value: 'add-media' },
    ]])
  })

  it('preserves Back without saving, resumes a saved step, and explicitly saves Finish on replay', async () => {
    persisted.settings.onboarding = { completed: false, last_step: 'add-media' }
    const first = setup()
    await screen.findByRole('heading', { name: 'Add a first file' })
    await first.user.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('heading', { name: 'Choose your settings' })).toBeInTheDocument()
    expect(desktopClient.patchSettings).not.toHaveBeenCalled()
    first.unmount()
    persisted.settings.onboarding = { completed: true, last_step: 'finish' }
    const replay = setup()
    await screen.findByRole('heading', { name: 'Welcome to Expletive Deleted' })
    for (let step = 0; step < 5; step++) await replay.user.click(screen.getByRole('button', { name: 'Save & Continue' }))
    await replay.user.click(screen.getByRole('button', { name: 'Finish setup' }))
    await waitFor(() => expect(onFinished).toHaveBeenCalledOnce())
    expect(vi.mocked(desktopClient.patchSettings).mock.calls.at(-1)?.[1]).toEqual([
      { field: 'onboarding.last_step', expected: 'finish', value: 'finish' },
      { field: 'onboarding.completed', expected: true, value: true },
    ])
  })
})
