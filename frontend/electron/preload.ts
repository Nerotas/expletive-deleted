import { contextBridge, ipcRenderer, webUtils } from 'electron'
import { unwrapInvokeResponse } from './ipc-response.js'

async function invoke<T>(method: string, params?: Record<string, unknown>): Promise<T> {
  return unwrapInvokeResponse(await ipcRenderer.invoke('expletive-deleted:invoke', method, params))
}

contextBridge.exposeInMainWorld('expletiveDeleted', {
  desktop: true,
  invoke,
  selectDirectory: (defaultPath?: string) => ipcRenderer.invoke('expletive-deleted:select-directory', defaultPath) as Promise<string | undefined>,
  selectFile: (defaultPath?: string) => ipcRenderer.invoke('expletive-deleted:select-file', defaultPath) as Promise<string | undefined>,
  selectDictionaryImport: () => ipcRenderer.invoke('expletive-deleted:select-dictionary-import') as Promise<string | undefined>,
  selectDictionaryExport: () => ipcRenderer.invoke('expletive-deleted:select-dictionary-export') as Promise<string | undefined>,
  openExternal: (url: string) => ipcRenderer.invoke('expletive-deleted:open-external', url) as Promise<void>,
  openTranscodeFolder: () => ipcRenderer.invoke('expletive-deleted:open-transcode-folder') as Promise<void>,
  openFile: (filePath: string) => ipcRenderer.invoke('expletive-deleted:open-file', filePath) as Promise<void>,
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
})
