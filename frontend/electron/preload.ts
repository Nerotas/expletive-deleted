import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('expletiveDeleted', {
  desktop: true,
  invoke: <T>(method: string, params?: Record<string, unknown>) => ipcRenderer.invoke('expletive-deleted:invoke', method, params) as Promise<T>,
  selectDirectory: (defaultPath?: string) => ipcRenderer.invoke('expletive-deleted:select-directory', defaultPath) as Promise<string | undefined>,
  selectFile: (defaultPath?: string) => ipcRenderer.invoke('expletive-deleted:select-file', defaultPath) as Promise<string | undefined>,
  selectDictionaryImport: () => ipcRenderer.invoke('expletive-deleted:select-dictionary-import') as Promise<string | undefined>,
  selectDictionaryExport: () => ipcRenderer.invoke('expletive-deleted:select-dictionary-export') as Promise<string | undefined>,
  openExternal: (url: string) => ipcRenderer.invoke('expletive-deleted:open-external', url) as Promise<void>,
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
})
