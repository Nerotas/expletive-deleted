export {}

declare global {
  interface Window {
    profanityCensor?: {
      desktop: boolean
      invoke: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
      selectDirectory: (defaultPath?: string) => Promise<string | undefined>
      selectFile: (defaultPath?: string) => Promise<string | undefined>
      selectDictionaryImport: () => Promise<string | undefined>
      selectDictionaryExport: () => Promise<string | undefined>
      openExternal: (url: string) => Promise<void>
      getPathForFile: (file: File) => string
    }
  }
}
