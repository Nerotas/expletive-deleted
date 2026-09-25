import { useQuery } from '@tanstack/react-query'
import type { AppUpdateInfo } from '../../../shared/bridge'
import { desktopClient } from '../../services/desktop-client'

const CACHE_KEY = 'expletive-deleted:update-check:v1'
const CACHE_DURATION_MS = 24 * 60 * 60 * 1000

type CachedUpdate = { checkedAt: number; result: AppUpdateInfo }

function isProjectUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && url.hostname === 'github.com'
      && url.pathname.startsWith('/Nerotas/expletive-deleted/')
  } catch {
    return false
  }
}

function cachedUpdate(currentVersion: string): AppUpdateInfo | undefined {
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null') as Partial<CachedUpdate> | null
    if (!cached || typeof cached.checkedAt !== 'number' || !cached.result) return undefined
    const result = cached.result
    if (result.currentVersion !== currentVersion || typeof result.latestVersion !== 'string'
      || typeof result.updateAvailable !== 'boolean' || !isProjectUrl(result.releaseUrl)
      || (result.downloadUrl !== undefined && !isProjectUrl(result.downloadUrl))
      || Date.now() - cached.checkedAt >= CACHE_DURATION_MS) return undefined
    return cached.result
  } catch {
    return undefined
  }
}

function storeUpdate(result: AppUpdateInfo): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ checkedAt: Date.now(), result } satisfies CachedUpdate))
  } catch { /* Update checks still work when browser storage is unavailable. */ }
}

export function useAppUpdate() {
  const appInfoQuery = useQuery({
    queryKey: ['app-info'],
    queryFn: desktopClient.getAppInfo,
    staleTime: Infinity,
  })
  const currentVersion = appInfoQuery.data?.version
  const updateQuery = useQuery({
    queryKey: ['app-update', currentVersion],
    enabled: appInfoQuery.data?.isPackaged === true,
    staleTime: Infinity,
    queryFn: async () => {
      if (!currentVersion) throw new Error('The application version is unavailable.')
      const cached = cachedUpdate(currentVersion)
      if (cached) return cached
      const result = await desktopClient.checkForUpdates()
      storeUpdate(result)
      return result
    },
  })

  const checkNow = async () => {
    try { localStorage.removeItem(CACHE_KEY) } catch { /* Continue without cache access. */ }
    return updateQuery.refetch()
  }
  const openUpdate = async () => {
    const info = updateQuery.data
    if (!info?.updateAvailable) return
    await desktopClient.openExternal(info.downloadUrl ?? info.releaseUrl)
  }

  return {
    appInfo: appInfoQuery.data,
    info: updateQuery.data,
    checking: appInfoQuery.isLoading || updateQuery.isFetching,
    error: updateQuery.error instanceof Error ? updateQuery.error.message : undefined,
    checkNow,
    openUpdate,
  }
}

export type AppUpdateController = ReturnType<typeof useAppUpdate>
