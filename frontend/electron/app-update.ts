import type { AppUpdateInfo } from '../shared/bridge.js'

const RELEASE_API_URL = 'https://api.github.com/repos/Nerotas/expletive-deleted/releases/latest'
const RELEASES_URL = 'https://github.com/Nerotas/expletive-deleted/releases'
const VERSION_PATTERN = /^v?(\d+)\.(\d+)\.(\d+)$/

type ReleaseAsset = { name?: unknown; browser_download_url?: unknown }
type ReleasePayload = { tag_name?: unknown; html_url?: unknown; assets?: unknown }

function versionParts(value: string): [number, number, number] {
  const match = VERSION_PATTERN.exec(value)
  if (!match) throw new Error(`GitHub returned an unsupported release version: ${value}`)
  return [Number(match[1]), Number(match[2]), Number(match[3])]
}

export function compareVersions(left: string, right: string): number {
  const leftParts = versionParts(left)
  const rightParts = versionParts(right)
  for (let index = 0; index < leftParts.length; index += 1) {
    const difference = leftParts[index] - rightParts[index]
    if (difference !== 0) return Math.sign(difference)
  }
  return 0
}

function validatedProjectUrl(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback
  const url = new URL(value)
  if (url.protocol !== 'https:' || url.hostname !== 'github.com' || !url.pathname.startsWith('/Nerotas/expletive-deleted/')) {
    throw new Error('GitHub returned an unexpected release link.')
  }
  return url.toString()
}

export async function checkForUpdates(currentVersion: string, request: typeof fetch = fetch): Promise<AppUpdateInfo> {
  versionParts(currentVersion)
  const response = await request(RELEASE_API_URL, {
    headers: {
      Accept: 'application/vnd.github+json',
      'User-Agent': `Expletive-Deleted/${currentVersion}`,
      'X-GitHub-Api-Version': '2022-11-28',
    },
    signal: AbortSignal.timeout(8000),
  })
  if (!response.ok) throw new Error(`GitHub update check failed with status ${response.status}.`)

  const payload = await response.json() as ReleasePayload
  if (typeof payload.tag_name !== 'string') throw new Error('GitHub returned release information without a version.')
  const latestVersion = payload.tag_name.replace(/^v/, '')
  versionParts(latestVersion)
  const releaseUrl = validatedProjectUrl(payload.html_url, `${RELEASES_URL}/tag/v${latestVersion}`)
  const expectedAssetName = `Expletive-Deleted-Setup-${latestVersion}-x64.exe`
  const assets = Array.isArray(payload.assets) ? payload.assets as ReleaseAsset[] : []
  const installer = assets.find((asset) => asset.name === expectedAssetName)
  const downloadUrl = installer
    ? validatedProjectUrl(installer.browser_download_url, releaseUrl)
    : undefined

  return {
    currentVersion,
    latestVersion,
    updateAvailable: compareVersions(latestVersion, currentVersion) > 0,
    releaseUrl,
    ...(downloadUrl ? { downloadUrl } : {}),
  }
}
