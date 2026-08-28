import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('profanityCensor', {
  desktop: true,
  invoke: <T>(method: string, params?: Record<string, unknown>) => ipcRenderer.invoke('profanity-censor:invoke', method, params) as Promise<T>,
  selectDirectory: (defaultPath?: string) => ipcRenderer.invoke('profanity-censor:select-directory', defaultPath) as Promise<string | undefined>,
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
})
