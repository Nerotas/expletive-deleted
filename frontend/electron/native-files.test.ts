import type { Dialog } from 'electron'
import { describe, expect, it, vi } from 'vitest'
import { assertRendererMethod, nativeFileOperations } from './native-files.js'
import type { TrustedRequest } from './ipc-security.js'

function fixture() {
  const invoke = vi.fn(async (method: string) => {
    if (method === 'native.export.prepare') return { token: 'selected', exists: false }
    if (method === 'native.output.prepare') return { token: 'selected' }
    if (method === 'native.output.check' || method === 'native.dictionary.export') return { path: 'C:\\selected.json' }
    return undefined
  })
  const dialog = {
    showSaveDialog: vi.fn(async () => ({ canceled: false, filePath: 'C:\\selected.json' })),
    showOpenDialog: vi.fn(async () => ({ canceled: false, filePaths: ['C:\\selected.json'] })),
    showMessageBox: vi.fn(async () => ({ response: 1 })),
  }
  const shell = { openPath: vi.fn(async () => '') }
  const request = { window: {}, assertCurrent: vi.fn() } as unknown as TrustedRequest
  return { invoke, dialog, shell, request, operations: nativeFileOperations(invoke, dialog as unknown as Dialog, shell) }
}

describe('native file ownership', () => {
  it.each(['dictionary.import', 'dictionary.export', 'native.output.prepare', 'native.output.check', 'native.release', 'native.export.prepare', 'native.dictionary.export', 'native.dictionary.import', '__proto__', 42])('rejects generic forwarding of %s', (method) => {
    expect(() => assertRendererMethod(method)).toThrow('approved native file selection')
  })
  it('permits the public backend contract', () => expect(() => assertRendererMethod('library.list')).not.toThrow())
  it('cancels without a backend write', async () => {
    const f = fixture()
    f.dialog.showSaveDialog.mockResolvedValue({ canceled: true, filePath: '' })
    expect(await f.operations.exportDictionary(f.request)).toEqual({ canceled: true })
    expect(f.invoke).not.toHaveBeenCalled()
  })
  it('exports only to the native selection and releases its token', async () => {
    const f = fixture()
    expect(await f.operations.exportDictionary(f.request)).toEqual({ canceled: false, path: 'C:\\selected.json' })
    expect(f.invoke).toHaveBeenCalledWith('native.export.prepare', { destination: 'C:\\selected.json' })
    expect(f.invoke).toHaveBeenCalledWith('native.dictionary.export', { token: 'selected', overwrite: false })
    expect(f.invoke).toHaveBeenLastCalledWith('native.release', { token: 'selected' })
  })
  it.each([0, 1])('binds replacement confirmation %s to the prepared token', async (response) => {
    const f = fixture()
    f.invoke.mockResolvedValueOnce({ token: 'selected', exists: true })
    f.dialog.showMessageBox.mockResolvedValue({ response })
    await f.operations.exportDictionary(f.request)
    expect(f.invoke.mock.calls.some(([method]) => method === 'native.dictionary.export')).toBe(response === 1)
    expect(f.invoke).toHaveBeenLastCalledWith('native.release', { token: 'selected' })
  })
  it('rejects a destroyed document after the picker and before any write', async () => {
    const f = fixture()
    vi.mocked(f.request.assertCurrent).mockImplementation(() => { throw new Error('document closed') })
    await expect(f.operations.exportDictionary(f.request)).rejects.toThrow('document closed')
    expect(f.invoke).not.toHaveBeenCalled()
  })
  it('surfaces changed destinations and releases their selection', async () => {
    const f = fixture()
    f.invoke.mockResolvedValueOnce({ token: 'selected', exists: true }).mockRejectedValueOnce(new Error('Output changed'))
    await expect(f.operations.exportDictionary(f.request)).rejects.toThrow('Output changed')
    expect(f.invoke).toHaveBeenLastCalledWith('native.release', { token: 'selected' })
  })
  it('surfaces unsupported paths before attempting an export', async () => {
    const f = fixture()
    f.invoke.mockRejectedValueOnce(new Error('Choose an ordinary .json'))
    await expect(f.operations.exportDictionary(f.request)).rejects.toThrow('.json')
    expect(f.invoke).toHaveBeenCalledTimes(1)
  })
  it('serializes overlapping picker calls', async () => {
    const f = fixture()
    let finish!: (value: { canceled: boolean; filePath: string }) => void
    f.dialog.showSaveDialog.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    const first = f.operations.exportDictionary(f.request)
    await expect(f.operations.exportDictionary(f.request)).rejects.toThrow('current file selection')
    finish({ canceled: true, filePath: '' })
    await first
  })
  it('hands off only the checked backend path and releases it on OS errors', async () => {
    const f = fixture()
    f.shell.openPath.mockResolvedValue('No player installed')
    await expect(f.operations.openOutput(f.request, 'queue-source')).rejects.toThrow('No player installed')
    expect(f.invoke).toHaveBeenCalledWith('native.output.prepare', { source: 'queue-source' })
    expect(f.shell.openPath).toHaveBeenCalledWith('C:\\selected.json')
    expect(f.invoke).toHaveBeenLastCalledWith('native.release', { token: 'selected' })
  })
  it('releases a playback lease when its document disappears during preparation', async () => {
    const f = fixture()
    vi.mocked(f.request.assertCurrent).mockImplementation(() => { throw new Error('document closed') })
    await expect(f.operations.openOutput(f.request, 'source')).rejects.toThrow('document closed')
    expect(f.shell.openPath).not.toHaveBeenCalled()
    expect(f.invoke).toHaveBeenLastCalledWith('native.release', { token: 'selected' })
  })
  it('imports exactly the selected path and catches picker failures', async () => {
    const f = fixture()
    await f.operations.importDictionary(f.request)
    expect(f.invoke).toHaveBeenCalledWith('native.dictionary.import', { source: 'C:\\selected.json' })
    f.dialog.showOpenDialog.mockRejectedValueOnce(new Error('picker failed'))
    await expect(f.operations.importDictionary(f.request)).rejects.toThrow('picker failed')
  })
})
