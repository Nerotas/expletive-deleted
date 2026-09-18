import type { DictionaryMutationResult, NativeFileResult } from './types/domain'

declare global {
  interface Window {
    expletiveDeleted?: {
      desktop: boolean
      invoke: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
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
