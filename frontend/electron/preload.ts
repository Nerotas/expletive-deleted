import { contextBridge, ipcRenderer, webUtils } from 'electron'
import { unwrapInvokeResponse } from './ipc-response.js'
import type { BackendState, RequestOptions } from '../shared/bridge.js'

async function invoke<T>(method: string, params?: Record<string, unknown>, options?: RequestOptions): Promise<T> {
  return unwrapInvokeResponse(await ipcRenderer.invoke('expletive-deleted:invoke', method, params, options))
}

contextBridge.exposeInMainWorld('expletiveDeleted', {
  desktop: true,
  invoke,
  // Error instances crossing contextBridge lose custom properties. Keep the
  // structured envelope until the typed renderer client creates its Error.
  request: (method: string, params?: Record<string, unknown>, options?: RequestOptions) =>
    ipcRenderer.invoke('expletive-deleted:invoke', method, params, options),
  getBackendState: () => ipcRenderer.invoke('expletive-deleted:backend-state') as Promise<BackendState>,
  onBackendState: (listener: (state: BackendState) => void) => {
    const receive = (_event: Electron.IpcRendererEvent, state: BackendState) => {
      if (Number.isSafeInteger(state?.generation) && ['running', 'exited', 'unavailable'].includes(state?.status)) {
        listener({ generation: state.generation, status: state.status })
      }
    }
    ipcRenderer.on('expletive-deleted:backend-state', receive)
    return () => ipcRenderer.removeListener('expletive-deleted:backend-state', receive)
  },
  restart: () => ipcRenderer.invoke('expletive-deleted:restart') as Promise<void>,
  selectDirectory: (defaultPath?: string) => ipcRenderer.invoke('expletive-deleted:select-directory', defaultPath) as Promise<string | undefined>,
  selectFile: (defaultPath?: string) => ipcRenderer.invoke('expletive-deleted:select-file', defaultPath) as Promise<string | undefined>,
  importDictionary: async () => unwrapInvokeResponse(await ipcRenderer.invoke('expletive-deleted:import-dictionary')),
  exportDictionary: async () => unwrapInvokeResponse(await ipcRenderer.invoke('expletive-deleted:export-dictionary')),
  openExternal: (url: string) => ipcRenderer.invoke('expletive-deleted:open-external', url) as Promise<void>,
  openTranscodeFolder: () => ipcRenderer.invoke('expletive-deleted:open-transcode-folder') as Promise<void>,
  openOutput: async (source: string) => unwrapInvokeResponse<void>(await ipcRenderer.invoke('expletive-deleted:open-output', source)),
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
})
