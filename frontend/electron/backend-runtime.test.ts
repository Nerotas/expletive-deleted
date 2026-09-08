import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { backendEnvironment, findBackendRoot } from './backend-runtime.js'

describe('backend runtime resolution', () => {
  it('uses first-party backend resources in a packaged application', () => {
    const resourcesPath = path.resolve('installed', 'resources')
    const expected = path.join(resourcesPath, 'app-backend')

    const result = findBackendRoot({
      isPackaged: true,
      resourcesPath,
      appPath: path.resolve('installed', 'resources', 'app.asar'),
      cwd: path.resolve('elsewhere'),
      moduleDirectory: path.resolve('installed', 'resources', 'app.asar', 'out', 'main'),
      exists: (candidate) => candidate === path.join(expected, 'scripts', 'desktop_bridge.py'),
    })

    expect(result).toBe(expected)
  })

  it('fails clearly when packaged backend resources are missing', () => {
    expect(() => findBackendRoot({
      isPackaged: true,
      resourcesPath: path.resolve('installed', 'resources'),
      appPath: path.resolve('installed', 'resources', 'app.asar'),
      cwd: path.resolve('elsewhere'),
      moduleDirectory: path.resolve('installed', 'resources', 'app.asar', 'out', 'main'),
      exists: () => false,
    })).toThrow('Reinstall Expletive Deleted')
  })

  it('does not treat the installed backend as a writable media root', () => {
    expect(backendEnvironment({ CENSOR_PROJECT_ROOT: String.raw`D:\Program Files\Expletive Deleted\resources\app-backend` }))
      .toMatchObject({ CENSOR_PROJECT_ROOT: '' })
  })

  it('passes Electron\'s app-data root to the Python bridge', () => {
    const localAppData = path.resolve('parent-local-app-data')

    expect(backendEnvironment({ LOCALAPPDATA: localAppData }))
      .toMatchObject({ CENSOR_APP_DATA_DIR: path.join(localAppData, 'ExpletiveDeleted') })
  })
})
