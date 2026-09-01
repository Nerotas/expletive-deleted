import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { createQueryClient } from './query-client'
import { desktopClient } from './services/desktop-client'
import type { Settings } from './types/domain'
import { defaultSettings, emptyDictionary, emptyDictionaryPage, readyCapabilities } from './test/fixtures'

function cloneSettings(settings: Settings): Settings {
  return structuredClone(settings)
}

function renderApp(route = '/') {
  const queryClient = createQueryClient()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}

describe('desktop application renderer', () => {
  let persisted: Settings

  beforeEach(() => {
    persisted = cloneSettings(defaultSettings)
    vi.spyOn(desktopClient, 'getSettings').mockImplementation(async () => cloneSettings(persisted))
    vi.spyOn(desktopClient, 'updateSettings').mockImplementation(async (settings) => {
      persisted = cloneSettings(settings)
      return cloneSettings(persisted)
    })
    vi.spyOn(desktopClient, 'getCapabilities').mockResolvedValue(readyCapabilities)
    vi.spyOn(desktopClient, 'getDictionaryInfo').mockResolvedValue(emptyDictionary)
    vi.spyOn(desktopClient, 'getDictionaryExclusions').mockResolvedValue(emptyDictionaryPage)
    vi.spyOn(desktopClient, 'getCensoredWords').mockResolvedValue({
      ...emptyDictionaryPage,
      target: 'censor',
    })
    vi.spyOn(desktopClient, 'getDiscoveredWords').mockResolvedValue({ words: [] })
    vi.spyOn(desktopClient, 'listLibrary').mockResolvedValue([])
    vi.spyOn(desktopClient, 'listArchive').mockResolvedValue([])
    vi.spyOn(desktopClient, 'listJobs').mockResolvedValue([])
    vi.spyOn(desktopClient, 'listJobEvents').mockResolvedValue([])
    vi.spyOn(desktopClient, 'submitJob').mockImplementation(async (source, mode) => ({
      id: 'submitted-job', source, mode, status: 'queued', progress_percent: 0, error: null,
    }))
    vi.spyOn(desktopClient, 'submitJobs').mockResolvedValue([])
    vi.spyOn(desktopClient, 'cancelJob').mockImplementation(async (jobId) => ({
      id: jobId, source: 'C:\\Media\\Ready\\movie.mkv', mode: 'censor', status: 'cancelled', progress_percent: 0, error: null,
    }))
    vi.spyOn(desktopClient, 'archiveSource').mockResolvedValue({})
    vi.spyOn(desktopClient, 'restoreArchiveSource').mockResolvedValue({})
    vi.spyOn(desktopClient, 'selectDirectory').mockResolvedValue(undefined)
    vi.spyOn(desktopClient, 'selectFile').mockResolvedValue(undefined)
    vi.spyOn(desktopClient, 'selectDictionaryImport').mockResolvedValue(undefined)
    vi.spyOn(desktopClient, 'selectDictionaryExport').mockResolvedValue(undefined)
    vi.spyOn(desktopClient, 'planDependencies').mockResolvedValue({
      plan_id: 'approved-plan',
      actions: [],
    })
    vi.spyOn(desktopClient, 'installDependencies').mockResolvedValue({})
    vi.spyOn(desktopClient, 'updateDictionary').mockResolvedValue(emptyDictionary)
    vi.spyOn(desktopClient, 'restoreDictionaryDefaults').mockResolvedValue(emptyDictionary)
    vi.spyOn(desktopClient, 'importDictionary').mockResolvedValue(emptyDictionary)
    vi.spyOn(desktopClient, 'exportDictionary').mockResolvedValue({ path: 'C:\\backup\\dictionary.json' })
    vi.spyOn(desktopClient, 'openExternal').mockResolvedValue()
    localStorage.clear()
  })

  it('shows a system check in progress before reporting readiness', async () => {
    let completeCheck: ((value: typeof readyCapabilities) => void) | undefined
    vi.mocked(desktopClient.getCapabilities).mockImplementationOnce(
      () => new Promise((resolve) => { completeCheck = resolve }),
    )
    renderApp('/')

    expect(screen.getByText('Checking system')).toBeInTheDocument()
    expect(screen.queryByText('Setup required')).not.toBeInTheDocument()

    await act(async () => completeCheck?.(readyCapabilities))
    expect(await screen.findByText('System ready')).toBeInTheDocument()
  })

  it('opens onboarding for fresh settings and gates components on live readiness', async () => {
    persisted.onboarding.completed = false
    vi.mocked(desktopClient.getCapabilities).mockResolvedValue({
      ...readyCapabilities,
      ready: false,
      ffmpeg: false,
      ffprobe: false,
    })
    const user = userEvent.setup()
    renderApp('/')

    expect(await screen.findByRole('heading', { name: 'Welcome to Expletive Deleted' })).toBeInTheDocument()
    expect(desktopClient.listLibrary).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /Continue/ }))

    expect(await screen.findByRole('heading', { name: 'Prepare required components' })).toBeInTheDocument()
    expect(screen.getByText('FFmpeg and FFprobe')).toBeInTheDocument()
    expect(screen.getByText('Speech recognition')).toBeInTheDocument()
    expect(screen.getByText('Whisper large-v3 model')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Continue/ })).toBeDisabled()
    expect(desktopClient.installDependencies).not.toHaveBeenCalled()
  })

  it('requires the supported large-v3 model even when aggregate capabilities are ready', async () => {
    persisted.onboarding.completed = false
    vi.mocked(desktopClient.getCapabilities).mockResolvedValue({
      ...readyCapabilities,
      whisper_model: 'medium',
    })
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: /Continue/ }))
    expect(await screen.findByText('Whisper large-v3 model')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Continue/ })).toBeDisabled()
  })

  it('finishes a reopened walkthrough through the complete atomic settings update', async () => {
    const user = userEvent.setup()
    renderApp('/onboarding')

    await user.click(await screen.findByRole('button', { name: /Continue/ }))
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    expect(await screen.findByRole('heading', { name: 'Prepare your dictionary' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Use default censored words/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Import a dictionary/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Continue/ }))

    await user.click(await screen.findByRole('button', { name: 'Karaoke' }))
    expect(screen.getByText('Not appropriate for mono audio')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    expect(await screen.findByDisplayValue('C:\\Media\\Ready')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Continue/ }))

    expect(await screen.findByText('Drag and drop')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    expect(await screen.findByText('Transcribe only')).toBeInTheDocument()
    expect(screen.getByText('Transcribe + Transcode')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    await user.click(await screen.findByRole('button', { name: 'Finish setup' }))

    await waitFor(() => expect(desktopClient.updateSettings).toHaveBeenLastCalledWith(
      expect.objectContaining({
        onboarding: { completed: true },
        censoring: expect.objectContaining({ stereo_method: 'karaoke' }),
      }),
    ))
    expect(await screen.findByText('Drop media here to add it')).toBeInTheDocument()
  })

  it('keeps a Karaoke draft without running Queue polling off the Queue route', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderApp('/settings')

    const karaoke = await screen.findByRole('button', { name: 'Karaoke' })
    await user.click(karaoke)
    expect(karaoke).toHaveAttribute('aria-pressed', 'true')

    await act(async () => { await vi.advanceTimersByTimeAsync(3_200) })

    expect(karaoke).toHaveAttribute('aria-pressed', 'true')
    expect(desktopClient.getSettings).toHaveBeenCalledTimes(1)
    expect(desktopClient.listLibrary).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('saves Karaoke and reloads it in a new renderer session', async () => {
    const user = userEvent.setup()
    const first = renderApp('/settings')
    await user.click(await screen.findByRole('button', { name: 'Karaoke' }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(desktopClient.updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({ censoring: expect.objectContaining({ stereo_method: 'karaoke' }) }),
    ))
    first.unmount()

    renderApp('/settings')
    expect(await screen.findByRole('button', { name: 'Karaoke' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('discards a draft locally and disables actions when the form is clean', async () => {
    const user = userEvent.setup()
    renderApp('/settings')
    await user.click(await screen.findByRole('button', { name: 'Karaoke' }))

    const discard = screen.getByRole('button', { name: 'Discard' })
    expect(discard).toBeEnabled()
    await user.click(discard)

    expect(screen.getByRole('button', { name: 'Drop audio' })).toHaveAttribute('aria-pressed', 'true')
    expect(discard).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('presents blank runtime paths as automatic detection rather than missing setup', async () => {
    renderApp('/settings')

    expect(await screen.findByLabelText('FFmpeg path override')).toHaveAttribute(
      'placeholder',
      'Using automatic detection',
    )
    expect(screen.getByLabelText('FFprobe path override')).toHaveAttribute(
      'placeholder',
      'Using automatic detection',
    )
    expect(screen.getByText(/they do not add FFmpeg command-line flags/i)).toBeInTheDocument()
    expect(screen.getByText('All required components are verified.')).toBeInTheDocument()
  })

  it('opens optional Ko-fi support only after an explicit Settings action', async () => {
    const user = userEvent.setup()
    renderApp('/settings')

    const support = await screen.findByRole('button', { name: 'Support development' })
    expect(screen.getByText(/does not unlock features or priority service/i)).toBeInTheDocument()
    expect(desktopClient.openExternal).not.toHaveBeenCalled()

    await user.click(support)
    expect(desktopClient.openExternal).toHaveBeenCalledWith('https://ko-fi.com/nicholaserotas')
  })

  it('retains the draft and reports an error when saving fails', async () => {
    vi.mocked(desktopClient.updateSettings).mockRejectedValueOnce(new Error('Disk is read-only'))
    const user = userEvent.setup()
    renderApp('/settings')
    const karaoke = await screen.findByRole('button', { name: 'Karaoke' })
    await user.click(karaoke)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Disk is read-only')
    expect(karaoke).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  })

  it('refreshes the persisted cache path after installing a Whisper model', async () => {
    const managedCache = 'C:\\Users\\Parent\\AppData\\Local\\ExpletiveDeleted\\models\\whisper'
    vi.mocked(desktopClient.getCapabilities).mockImplementation(async () => ({
      ...readyCapabilities,
      ready: persisted.runtime.whisper_cache !== null,
      whisper_model_ready: persisted.runtime.whisper_cache !== null,
    }))
    vi.mocked(desktopClient.installDependencies).mockImplementationOnce(async () => {
      persisted.runtime.whisper_cache = managedCache
      return {}
    })
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Get' }))
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    await screen.findByText('Installation complete and verified')
    await user.click(screen.getByRole('link', { name: 'Settings' }))

    expect(await screen.findByDisplayValue(managedCache)).toBeInTheDocument()
    expect(desktopClient.getSettings).toHaveBeenCalledTimes(2)
  })

  it('renders the empty Queue and performs a Dictionary add through typed actions', async () => {
    const user = userEvent.setup()
    renderApp('/')
    expect(await screen.findByText('Drop media here to add it')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Dictionary' }))
    await user.type(await screen.findByRole('textbox', { name: 'Word or phrase' }), 'example')
    await user.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(desktopClient.updateDictionary).toHaveBeenCalledWith(
      'add',
      'censor',
      'example',
    ))
  })

  it('requires confirmation to reveal censored words while leaving exclusions visible', async () => {
    vi.mocked(desktopClient.getDictionaryInfo).mockResolvedValueOnce({
      dictionary_path: 'C:\\Users\\Parent\\AppData\\Local\\ExpletiveDeleted\\dictionary',
      schema_version: 2,
      seeded_from_default_version: 1,
    })
    vi.mocked(desktopClient.getDictionaryExclusions).mockResolvedValue({
      target: 'exclude',
      items: [{ value: 'example-exclusion', added_at: '2026-09-01T12:00:00Z', source: 'user' }],
      total: 1, page: 1, page_size: 25, total_pages: 1,
    })
    vi.mocked(desktopClient.getCensoredWords).mockResolvedValueOnce({
      target: 'censor',
      items: [
        { value: 'example-censor-one', added_at: '1970-01-01T00:00:00Z', source: 'default' },
        { value: 'example-censor-two', added_at: '2026-09-01T13:00:00Z', source: 'imported' },
      ],
      total: 2, page: 1, page_size: 25, total_pages: 1,
    })

    const user = userEvent.setup()
    renderApp('/dictionary')

    expect(await screen.findByText('example-exclusion')).toBeInTheDocument()
    expect(screen.queryByText('example-censor-one')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove example-censor-one' })).not.toBeInTheDocument()
    expect(screen.getByText('Format 2 · defaults 1')).toBeInTheDocument()
    expect(screen.getByText('User')).toBeInTheDocument()
    expect(desktopClient.getDictionaryInfo).toHaveBeenCalledOnce()
    expect(desktopClient.getDictionaryExclusions).toHaveBeenCalledOnce()
    expect(desktopClient.getDiscoveredWords).toHaveBeenCalledOnce()
    expect(desktopClient.getCensoredWords).not.toHaveBeenCalled()
    expect(desktopClient.listLibrary).not.toHaveBeenCalled()
    expect(desktopClient.listArchive).not.toHaveBeenCalled()
    expect(desktopClient.listJobs).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Censored words' }))
    let confirmation = screen.getByRole('dialog', { name: 'Reveal censored words?' })
    expect(screen.queryByText('example-censor-one')).not.toBeInTheDocument()
    await user.click(within(confirmation).getByRole('button', { name: 'Cancel' }))
    expect(desktopClient.getCensoredWords).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Censored words' }))
    confirmation = screen.getByRole('dialog', { name: 'Reveal censored words?' })
    await user.click(within(confirmation).getByRole('button', { name: 'Reveal words' }))
    expect(await screen.findByText('example-censor-one')).toBeInTheDocument()
    expect(desktopClient.getCensoredWords).toHaveBeenCalledOnce()
    expect(screen.getByText('example-censor-two')).toBeInTheDocument()
    expect(screen.getByText('Default', { selector: 'td' })).toBeInTheDocument()
    expect(screen.getByText('Imported')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Exclusions' }))
    expect(screen.queryByText('example-censor-one')).not.toBeInTheDocument()
    expect(await screen.findByText('example-exclusion')).toBeInTheDocument()
  })

  it('confirms restore and forwards selected dictionary import and export paths', async () => {
    const user = userEvent.setup()
    vi.mocked(desktopClient.selectDictionaryImport).mockResolvedValueOnce('C:\\backup\\import.json')
    vi.mocked(desktopClient.selectDictionaryExport).mockResolvedValueOnce('C:\\backup\\export.json')
    renderApp('/dictionary')

    await user.click(await screen.findByRole('button', { name: 'Restore defaults' }))
    expect(desktopClient.restoreDictionaryDefaults).not.toHaveBeenCalled()
    const confirmation = screen.getByRole('dialog', { name: 'Restore default dictionary?' })
    await user.click(within(confirmation).getByRole('button', { name: 'Restore defaults' }))
    await waitFor(() => expect(desktopClient.restoreDictionaryDefaults).toHaveBeenCalledOnce())

    await user.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(desktopClient.importDictionary).toHaveBeenCalledWith('C:\\backup\\import.json'))
    await user.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() => expect(desktopClient.exportDictionary).toHaveBeenCalledWith('C:\\backup\\export.json'))
  })

  it('turns a stalled Dictionary request into a retryable error', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(desktopClient.getDictionaryExclusions).mockImplementationOnce(
      () => new Promise(() => undefined),
    )

    renderApp('/dictionary')

    expect(screen.getByRole('textbox', { name: 'Word or phrase' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Censored words' })).toBeInTheDocument()
    expect(screen.getByText('Loading dictionary entries')).toBeInTheDocument()
    expect(screen.queryByText('No matching entries.')).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(15_000))
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByText(/censor dictionary did not respond/i)).toBeInTheDocument()
  })

  it('submits each explicit row action with its required mode', async () => {
    const source = 'C:\\Media\\Ready\\movie.mkv'
    vi.mocked(desktopClient.listLibrary).mockResolvedValue([{
      source,
      status: 'ready',
      transcript: null,
      output: null,
    }])
    const user = userEvent.setup()
    renderApp('/')

    await screen.findByText('movie.mkv')
    await user.click(await screen.findByRole('button', { name: 'Transcribe only' }))
    await waitFor(() => expect(desktopClient.submitJob).toHaveBeenCalledWith(source, 'report_only'))
    await user.click(screen.getByRole('button', { name: 'Transcribe + Transcode' }))

    await waitFor(() => expect(desktopClient.submitJob).toHaveBeenCalledWith(source, 'censor'))
  })

  it('offers finished files a fresh transcript or an atomic retranscode request', async () => {
    const source = 'C:\\Media\\Ready\\movie.mkv'
    vi.mocked(desktopClient.listLibrary).mockResolvedValue([{
      source,
      status: 'finished',
      transcript: 'C:\\Media\\Transcripts\\movie-transcript.json',
      output: 'C:\\Media\\Finished\\movie-censored.mkv',
    }])
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Retranscribe' }))
    await waitFor(() => expect(desktopClient.submitJob).toHaveBeenCalledWith(
      source,
      'report_only',
      { force_transcribe: true },
    ))

    const retranscode = screen.getByRole('button', { name: 'Retranscode' })
    await waitFor(() => expect(retranscode).toBeEnabled())
    await user.click(retranscode)
    await waitFor(() => expect(desktopClient.submitJob).toHaveBeenCalledWith(
      source,
      'censor',
      { overwrite_output: true },
    ))
  })

  it('queues selected files in displayed order and retains rejected selections', async () => {
    const alpha = 'C:\\Media\\Ready\\alpha.mkv'
    const zulu = 'C:\\Media\\Ready\\zulu.mkv'
    vi.mocked(desktopClient.listLibrary).mockResolvedValue([
      { source: zulu, status: 'ready', transcript: null, output: null },
      { source: alpha, status: 'ready', transcript: null, output: null },
    ])
    vi.mocked(desktopClient.submitJobs).mockResolvedValueOnce([
      {
        source: alpha,
        status: 'queued',
        job: { id: 'alpha-job', source: alpha, mode: 'censor', status: 'queued', progress_percent: 0, error: null },
      },
      { source: zulu, status: 'rejected', code: 'already_queued', detail: 'Already queued' },
    ])
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Select all shown' }))
    await user.click(screen.getByRole('button', { name: 'Queue transcribe + transcode' }))

    await waitFor(() => expect(desktopClient.submitJobs).toHaveBeenCalledWith([alpha, zulu], 'censor'))
    expect(screen.getByRole('checkbox', { name: 'Select alpha.mkv' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Select zulu.mkv' })).toBeChecked()
    expect(await screen.findByRole('alert')).toHaveTextContent('1 queued; 1 could not be queued')
  })

  it('shows queue positions, filters active and waiting work, and removes only a waiting job', async () => {
    const active = 'C:\\Media\\Ready\\active.mkv'
    const first = 'C:\\Media\\Ready\\first.mkv'
    const second = 'C:\\Media\\Ready\\second.mkv'
    vi.mocked(desktopClient.listLibrary).mockResolvedValue([
      { source: second, status: 'ready', transcript: null, output: null },
      { source: active, status: 'ready', transcript: null, output: null },
      { source: first, status: 'ready', transcript: null, output: null },
    ])
    vi.mocked(desktopClient.listJobs).mockResolvedValue([
      { id: 'active-job', source: active, mode: 'censor', status: 'transcribing', progress_percent: 20, error: null },
      { id: 'first-job', source: first, mode: 'report_only', status: 'queued', progress_percent: 0, error: null },
      { id: 'second-job', source: second, mode: 'censor', status: 'queued', progress_percent: 0, error: null },
    ])
    const user = userEvent.setup()
    renderApp('/')

    expect(await screen.findByText('#1')).toBeInTheDocument()
    expect(screen.getByText('#2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel active job' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel job' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Queued 2/ }))
    expect(screen.queryByText('active.mkv')).not.toBeInTheDocument()
    expect(screen.getByText('first.mkv')).toBeInTheDocument()
    expect(screen.getByText('second.mkv')).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: 'Remove from queue' })[0])
    await waitFor(() => expect(desktopClient.cancelJob).toHaveBeenCalledWith('first-job'))
    expect(desktopClient.cancelJob).not.toHaveBeenCalledWith('active-job')
  })

  it('sorts visible queue rows by file name', async () => {
    vi.mocked(desktopClient.listLibrary).mockResolvedValue([
      { source: 'C:\\Media\\Ready\\zulu.mkv', status: 'ready', transcript: null, output: null },
      { source: 'C:\\Media\\Ready\\alpha.mkv', status: 'ready', transcript: null, output: null },
    ])
    const user = userEvent.setup()
    renderApp('/')

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Sort' }), 'name')
    const fileRows = screen.getAllByRole('row').slice(1)
    expect(fileRows[0]).toHaveTextContent('alpha.mkv')
    expect(fileRows[1]).toHaveTextContent('zulu.mkv')
  })

  it('shows archived originals in the Queue archive view', async () => {
    vi.mocked(desktopClient.listArchive).mockResolvedValueOnce([{
      source: 'C:\\Media\\Processed\\movie.mkv',
      relative_path: 'movie.mkv',
      size_bytes: 2_048,
      archived_at: '2026-08-28T12:00:00+00:00',
    }])
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('tab', { name: /archive/i }))
    expect((await screen.findAllByText('movie.mkv')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Return to Queue' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete permanently' })).toBeInTheDocument()
  })

  it('shows source, destination, and size before an external retrieval can begin', async () => {
    vi.mocked(desktopClient.getCapabilities).mockResolvedValue({
      ...readyCapabilities,
      ready: false,
      ffmpeg: false,
      ffprobe: false,
    })
    vi.mocked(desktopClient.planDependencies).mockResolvedValueOnce({
      plan_id: 'ffmpeg-plan',
      actions: [{
        id: 'download-managed-ffmpeg-runtime',
        dependencies: ['ffmpeg', 'ffprobe'],
        description: 'Download and verify FFmpeg and FFprobe',
        source_name: 'static-ffmpeg platform binaries',
        source_url: 'https://pypi.org/project/static-ffmpeg/',
        estimated_download_bytes: 1073741824,
        destination: 'C:\\Users\\Parent\\AppData\\Local\\ExpletiveDeleted\\dependencies\\ffmpeg',
      }],
    })
    const user = userEvent.setup()
    renderApp('/')

    await user.click((await screen.findAllByRole('button', { name: 'Get' }))[0])

    expect(await screen.findByRole('dialog', { name: 'Retrieve required components?' })).toBeInTheDocument()
    expect(screen.getByText('static-ffmpeg platform binaries')).toBeInTheDocument()
    expect(screen.getByText(/ExpletiveDeleted/)).toBeInTheDocument()
    expect(screen.getByText('1.0 GB (approximately)')).toBeInTheDocument()
    expect(desktopClient.installDependencies).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(desktopClient.installDependencies).not.toHaveBeenCalled()
  })

  it('returns an archived original to Ready', async () => {
    const source = 'C:\\Media\\Processed\\movie.mkv'
    vi.mocked(desktopClient.listArchive).mockResolvedValue([{
      source,
      relative_path: 'movie.mkv',
      size_bytes: 2_048,
      archived_at: '2026-08-28T12:00:00+00:00',
    }])
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('tab', { name: /archive/i }))
    await user.click(screen.getByRole('button', { name: 'Return to Queue' }))

    await waitFor(() => expect(desktopClient.restoreArchiveSource).toHaveBeenCalledWith(source))
  })
})
