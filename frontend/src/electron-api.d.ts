interface Window {
  profanityCensor: {
    desktop: boolean
    invoke<T>(method: string, params?: Record<string, unknown>): Promise<T>
    selectDirectory(defaultPath?: string): Promise<string | undefined>
  }
}
