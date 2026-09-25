import type { DictionaryMutationResult, NativeFileResult } from './types/domain'
import type { AppInfo, AppUpdateInfo, BackendState, RequestOptions } from '../shared/bridge'

declare global {
  interface Window {
    expletiveDeleted?: {
      desktop: boolean
      invoke: <T>(method: string, params?: Record<string, unknown>, options?: RequestOptions) => Promise<T>
      request: <T>(method: string, params?: Record<string, unknown>, options?: RequestOptions) => Promise<import('../shared/ipc-response').InvokeResponse<T>>
      getAppInfo: () => Promise<AppInfo>
      checkForUpdates: () => Promise<AppUpdateInfo>
      getBackendState: () => Promise<BackendState>
      onBackendState: (listener: (state: BackendState) => void) => () => void
      restart: () => Promise<void>
      selectDirectory: (defaultPath?: string) => Promise<string | undefined>
      selectFile: (defaultPath?: string) => Promise<string | undefined>
      importDictionary: () => Promise<NativeFileResult<{ result: DictionaryMutationResult }>>
      exportDictionary: () => Promise<NativeFileResult<{ path: string }>>
      openExternal: (url: string) => Promise<void>
      openTranscodeFolder: () => Promise<void>
      openOutput: (source: string) => Promise<void>
      getPathForFile: (file: File) => string
    }
  }
}
