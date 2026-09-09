import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { backendEnvironment, findBackendRoot, findBundledRuntime } from './backend-runtime.js'

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

  it('discovers only a complete bundled processing runtime', () => {
    const resourcesPath = path.resolve('installed', 'resources')
    const runtimeRoot = path.join(resourcesPath, 'app-runtime')
    const python = path.join(runtimeRoot, 'python', 'python.exe')
    const ffmpeg = path.join(runtimeRoot, 'ffmpeg', 'ffmpeg.exe')
    const ffprobe = path.join(runtimeRoot, 'ffmpeg', 'ffprobe.exe')

    expect(findBundledRuntime(resourcesPath, 'win32', (candidate) => [python, ffmpeg, ffprobe].includes(candidate)))
      .toEqual({ python, ffmpeg, ffprobe })
    expect(findBundledRuntime(resourcesPath, 'win32', (candidate) => candidate !== ffprobe))
      .toEqual({})
  })

  it('passes Electron\'s app-data root to the Python bridge', () => {
    const localAppData = path.resolve('parent-local-app-data')

    const bundledRoot = path.resolve('installed', 'resources', 'app-runtime')
    const bundledFfmpeg = path.join(bundledRoot, 'ffmpeg', 'ffmpeg.exe')
    const bundledFfprobe = path.join(bundledRoot, 'ffmpeg', 'ffprobe.exe')

    expect(backendEnvironment(
      { LOCALAPPDATA: localAppData },
      {
        python: path.join(bundledRoot, 'python', 'python.exe'),
        ffmpeg: bundledFfmpeg,
        ffprobe: bundledFfprobe,
      },
    )).toMatchObject({
      CENSOR_APP_DATA_DIR: path.join(localAppData, 'ExpletiveDeleted'),
      CENSOR_FFMPEG: bundledFfmpeg,
      CENSOR_FFPROBE: bundledFfprobe,
      CENSOR_BUNDLED_RUNTIME: '1',
      PATH: expect.stringContaining(path.join('app-runtime', 'ffmpeg')),
    })
  })
})
