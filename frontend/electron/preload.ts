import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('profanityCensor', {
  desktop: true,
  invoke: <T>(method: string, params?: Record<string, unknown>) => ipcRenderer.invoke('profanity-censor:invoke', method, params) as Promise<T>,
  selectDirectory: (defaultPath?: string) => ipcRenderer.invoke('profanity-censor:select-directory', defaultPath) as Promise<string | undefined>,
  selectFile: (defaultPath?: string) => ipcRenderer.invoke('profanity-censor:select-file', defaultPath) as Promise<string | undefined>,
  selectDictionaryImport: () => ipcRenderer.invoke('profanity-censor:select-dictionary-import') as Promise<string | undefined>,
  selectDictionaryExport: () => ipcRenderer.invoke('profanity-censor:select-dictionary-export') as Promise<string | undefined>,
  openExternal: (url: string) => ipcRenderer.invoke('profanity-censor:open-external', url) as Promise<void>,
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
})
