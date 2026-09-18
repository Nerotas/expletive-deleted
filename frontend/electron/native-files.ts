import type { Dialog, Shell } from 'electron'
import type { TrustedRequest } from './ipc-security.js'

// Only these public operations may travel through generic renderer invoke.
const rendererMethods = new Set([
  'settings.get', 'settings.update', 'capabilities.get', 'library.list', 'library.archive', 'library.import',
  'archive.list', 'archive.restore', 'archive.purge', 'jobs.list', 'jobs.get', 'jobs.submit', 'jobs.submit_many',
  'jobs.events', 'jobs.cancel', 'downloads.list', 'downloads.submit', 'downloads.events', 'downloads.cancel',
  'dictionary.info', 'dictionary.exclusions', 'dictionary.censored', 'dictionary.discovered',
  'dictionary.add', 'dictionary.remove', 'dictionary.restore_defaults', 'reviews.list',
  'dependencies.plan', 'dependencies.install', 'dependencies.status', 'dependencies.cancel',
  'dependencies.inspect_ffmpeg', 'dependencies.locate_ffmpeg', 'dependencies.locate_model', 'dependencies.locate_ytdlp',
])

export function assertRendererMethod(method: unknown): asserts method is string {
  if (typeof method !== 'string' || !rendererMethods.has(method)) {
    throw Object.assign(new Error('This operation requires an approved native file selection.'), { code: 'native_file_rejected' })
  }
}

type Invoke = (method: string, params?: Record<string, unknown>) => Promise<unknown>
type Selection = { token: string; exists?: boolean }

export function nativeFileOperations(invoke: Invoke, dialog: Pick<Dialog, 'showOpenDialog' | 'showSaveDialog' | 'showMessageBox'>, shell: Pick<Shell, 'openPath'>) {
  let busy = false
  const run = async <T>(action: () => Promise<T>): Promise<T> => {
    if (busy) throw new Error('Finish the current file selection before starting another.')
    busy = true
    try { return await action() } finally { busy = false }
  }
  const release = (token: string) => invoke('native.release', { token }).catch(() => undefined)
  return {
    openOutput: (request: TrustedRequest, source: string) => run(async () => {
      const { token } = await invoke('native.output.prepare', { source }) as Selection
      try {
        request.assertCurrent()
        const { path } = await invoke('native.output.check', { token }) as { path: string }
        request.assertCurrent()
        const error = await shell.openPath(path)
        if (error) throw new Error(`Could not open the censored file: ${error}`)
      } finally { await release(token) }
    }),
    importDictionary: (request: TrustedRequest) => run(async () => {
      const choice = await dialog.showOpenDialog(request.window, {
        properties: ['openFile'], filters: [{ name: 'Expletive Deleted dictionary', extensions: ['json'] }],
      })
      request.assertCurrent()
      if (choice.canceled || !choice.filePaths[0]) return { canceled: true as const }
      const result = await invoke('native.dictionary.import', { source: choice.filePaths[0] })
      return { canceled: false as const, result }
    }),
    exportDictionary: (request: TrustedRequest) => run(async () => {
      const choice = await dialog.showSaveDialog(request.window, {
        defaultPath: 'expletive-deleted-dictionary.json',
        filters: [{ name: 'Expletive Deleted dictionary', extensions: ['json'] }],
      })
      request.assertCurrent()
      if (choice.canceled || !choice.filePath) return { canceled: true as const }
      const selection = await invoke('native.export.prepare', { destination: choice.filePath }) as Selection
      try {
        request.assertCurrent()
        let overwrite = false
        if (selection.exists) {
          // Confirm after Python captures the file version, so replacement consent
          // cannot silently transfer to a different file arriving during the dialog.
          const confirmation = await dialog.showMessageBox(request.window, {
            type: 'warning', buttons: ['Cancel', 'Replace'], defaultId: 0, cancelId: 0,
            message: 'Replace this dictionary backup?', detail: choice.filePath, noLink: true,
          })
          request.assertCurrent()
          if (confirmation.response !== 1) return { canceled: true as const }
          overwrite = true
        }
        const result = await invoke('native.dictionary.export', { token: selection.token, overwrite }) as { path: string }
        return { canceled: false as const, ...result }
      } finally { await release(selection.token) }
    }),
  }
}
