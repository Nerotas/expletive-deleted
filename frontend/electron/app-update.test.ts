import { describe, expect, it, vi } from 'vitest'
import { checkForUpdates, compareVersions } from './app-update.js'

function releaseResponse(version: string, assets: unknown[] = []) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      tag_name: `v${version}`,
      html_url: `https://github.com/Nerotas/expletive-deleted/releases/tag/v${version}`,
      assets,
    }),
  } as Response
}

describe('application updates', () => {
  it('compares major, minor, and patch versions numerically', () => {
    expect(compareVersions('1.10.0', '1.9.9')).toBe(1)
    expect(compareVersions('2.0.0', '2.0.0')).toBe(0)
    expect(compareVersions('1.4.1', '1.4.2')).toBe(-1)
  })

  it('returns the validated installer for a newer stable release', async () => {
    const downloadUrl = 'https://github.com/Nerotas/expletive-deleted/releases/download/v1.4.3/Expletive-Deleted-Setup-1.4.3-x64.exe'
    const request = vi.fn(async () => releaseResponse('1.4.3', [{
      name: 'Expletive-Deleted-Setup-1.4.3-x64.exe',
      browser_download_url: downloadUrl,
    }])) as unknown as typeof fetch

    await expect(checkForUpdates('1.4.2', request)).resolves.toEqual({
      currentVersion: '1.4.2',
      latestVersion: '1.4.3',
      updateAvailable: true,
      releaseUrl: 'https://github.com/Nerotas/expletive-deleted/releases/tag/v1.4.3',
      downloadUrl,
    })
  })

  it('does not offer an older release as an update', async () => {
    const request = vi.fn(async () => releaseResponse('1.4.1')) as unknown as typeof fetch
    const result = await checkForUpdates('1.4.2', request)
    expect(result.updateAvailable).toBe(false)
  })

  it('rejects release links outside the project repository', async () => {
    const request = vi.fn(async () => ({
      ...releaseResponse('1.4.3'),
      json: async () => ({ tag_name: 'v1.4.3', html_url: 'https://example.com/download', assets: [] }),
    } as Response)) as unknown as typeof fetch
    await expect(checkForUpdates('1.4.2', request)).rejects.toThrow('unexpected release link')
  })
})
