export type BackendState = { generation: number; status: 'running' | 'exited' | 'unavailable' }
export type RequestOptions = { timeoutMs?: number; generation?: number }
export const SYSTEM_CHECK_TIMEOUT_MS = 60_000
export type AppInfo = { version: string; isPackaged: boolean }
export type AppUpdateInfo = {
  currentVersion: string
  latestVersion: string
  updateAvailable: boolean
  releaseUrl: string
  downloadUrl?: string
}
