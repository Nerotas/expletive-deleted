import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { backendEnvironment, findBackendRoot, findBundledRuntime, findPythonRuntime, requireBundledRuntime } from './backend-runtime.js'

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

  it('discovers only the bundled private Python runtime', () => {
    const resourcesPath = path.resolve('installed', 'resources')
    const runtimeRoot = path.join(resourcesPath, 'app-runtime')
    const python = path.join(runtimeRoot, 'python', 'python.exe')
    const ffmpeg = path.join(runtimeRoot, 'ffmpeg', 'ffmpeg.exe')

    expect(findBundledRuntime(resourcesPath, 'win32', (candidate) => [python, ffmpeg].includes(candidate)))
      .toEqual({ python })
    expect(findBundledRuntime(resourcesPath, 'win32', (candidate) => candidate === python))
      .toEqual({ python })
  })

  it('fails closed when the private Python runtime is missing', () => {
    const resourcesPath = path.resolve('installed', 'resources')
    const runtimeRoot = path.join(resourcesPath, 'app-runtime')
    const manifest = path.join(runtimeRoot, 'runtime-manifest.json')
    const python = path.join(runtimeRoot, 'python', 'python.exe')

    expect(requireBundledRuntime(resourcesPath, 'win32', (candidate) => [manifest, python].includes(candidate)))
      .toEqual({ python })
    expect(requireBundledRuntime(resourcesPath, 'win32', () => false)).toEqual({})
  })

  it('passes Electron\'s app-data root to the Python bridge', () => {
    const localAppData = path.resolve('parent-local-app-data')

    const bundledRoot = path.resolve('installed', 'resources', 'app-runtime')
    expect(backendEnvironment(
      { LOCALAPPDATA: localAppData },
      { python: path.join(bundledRoot, 'python', 'python.exe') },
    )).toMatchObject({
      CENSOR_APP_DATA_DIR: path.join(localAppData, 'ExpletiveDeleted'),
      CENSOR_BUNDLED_RUNTIME: '1',
      CENSOR_PYTHON_PACKAGES_DIR: path.join(localAppData, 'ExpletiveDeleted', 'dependencies', 'python'),
      PYTHONPATH: path.join(localAppData, 'ExpletiveDeleted', 'dependencies', 'python'),
      PYTHONNOUSERSITE: '1',
    })
  })

  it('uses a working bundled Python without probing system interpreters', () => {
    const bundledPython = path.resolve('installed', 'resources', 'app-runtime', 'python', 'python.exe')
    const probes: string[] = []

    expect(findPythonRuntime(path.resolve('.'), 'win32', { CENSOR_PYTHON: 'system-python' }, bundledPython, (command) => {
      probes.push(command)
      return true
    })).toEqual({ command: bundledPython, args: ['-m', 'scripts.desktop_bridge'] })
    expect(probes).toEqual([bundledPython])
  })

  it('fails closed when the bundled Python cannot start', () => {
    const bundledPython = path.resolve('installed', 'resources', 'app-runtime', 'python', 'python.exe')
    const probes: string[] = []

    expect(() => findPythonRuntime(path.resolve('.'), 'win32', { CENSOR_PYTHON: 'system-python' }, bundledPython, (command) => {
      probes.push(command)
      return false
    })).toThrow('private Python runtime could not start')
    expect(probes).toEqual([bundledPython])
  })
})
