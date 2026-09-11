import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'

export type BackendRuntime = {
  root: string
  command: string
  args: string[]
}

export type BundledRuntimePaths = {
  python?: string
}

type PythonProbe = (command: string, args: string[]) => boolean

export function findBundledRuntime(
  resourcesPath: string,
  platform: NodeJS.Platform,
  exists: (candidate: string) => boolean = existsSync,
): BundledRuntimePaths {
  const executableName = platform === 'win32' ? 'python.exe' : 'python'
  const runtimeRoot = path.join(resourcesPath, 'app-runtime')
  const python = path.join(runtimeRoot, 'python', executableName)

  if (!exists(python)) return {}
  return { python }
}

export function requireBundledRuntime(
  resourcesPath: string,
  platform: NodeJS.Platform,
  exists: (candidate: string) => boolean = existsSync,
): BundledRuntimePaths {
  const manifest = path.join(resourcesPath, 'app-runtime', 'runtime-manifest.json')
  if (!exists(manifest)) return {}
  const runtime = findBundledRuntime(resourcesPath, platform, exists)
  if (runtime.python) return runtime
  throw new Error('The installed private Python runtime is incomplete. Reinstall Expletive Deleted.')
}

export function backendEnvironment(
  environment: NodeJS.ProcessEnv = process.env,
  bundledRuntime: BundledRuntimePaths = {},
): NodeJS.ProcessEnv {
  const localAppData = environment.LOCALAPPDATA?.trim()
  const appDataRoot = environment.CENSOR_APP_DATA_DIR?.trim()
    || (localAppData ? path.join(localAppData, 'ExpletiveDeleted') : undefined)
  const bundledPythonRuntime = Boolean(bundledRuntime.python)
  const managedPythonPackages = appDataRoot
    ? path.join(appDataRoot, 'dependencies', 'python')
    : undefined

  return {
    ...environment,
    CENSOR_PROJECT_ROOT: '',
    ...(appDataRoot ? { CENSOR_APP_DATA_DIR: appDataRoot } : {}),
    ...(bundledPythonRuntime ? { CENSOR_BUNDLED_RUNTIME: '1' } : {}),
    ...(bundledPythonRuntime && managedPythonPackages
      ? {
          CENSOR_PYTHON_PACKAGES_DIR: managedPythonPackages,
          PYTHONPATH: managedPythonPackages,
          PYTHONNOUSERSITE: '1',
        }
      : {}),
  }
}

type BackendRootOptions = {
  isPackaged: boolean
  resourcesPath: string
  appPath: string
  cwd: string
  moduleDirectory: string
  exists?: (candidate: string) => boolean
}

export function findBackendRoot({
  isPackaged,
  resourcesPath,
  appPath,
  cwd,
  moduleDirectory,
  exists = existsSync,
}: BackendRootOptions): string {
  if (isPackaged) {
    const packagedRoot = path.join(resourcesPath, 'app-backend')
    if (exists(path.join(packagedRoot, 'scripts', 'desktop_bridge.py'))) return packagedRoot
    throw new Error('The installed local processing service is missing. Reinstall Expletive Deleted.')
  }

  for (const start of [appPath, cwd, moduleDirectory]) {
    for (let candidate = path.resolve(start); ; candidate = path.dirname(candidate)) {
      if (exists(path.join(candidate, 'scripts', 'desktop_bridge.py'))) return candidate
      const parent = path.dirname(candidate)
      if (parent === candidate) break
    }
  }
  throw new Error('Could not find scripts/desktop_bridge.py. Start the desktop app from the repository checkout.')
}

export function findPythonRuntime(
  root: string,
  platform: NodeJS.Platform,
  environment: NodeJS.ProcessEnv = process.env,
  bundledPython?: string,
  probe: PythonProbe = (command, args) => spawnSync(command, args, {
    encoding: 'utf8',
    windowsHide: true,
    timeout: 10_000,
  }).status === 0,
): Omit<BackendRuntime, 'root'> {
  const configured = environment.CENSOR_PYTHON?.trim()
  const versionCheck = 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'
  if (bundledPython) {
    if (probe(bundledPython, ['-c', versionCheck])) {
      return { command: bundledPython, args: ['-m', 'scripts.desktop_bridge'] }
    }
    throw new Error('The installed private Python runtime could not start. Reinstall Expletive Deleted.')
  }

  const candidates: Array<{ command: string; prefix: string[] }> = []
  if (configured) candidates.push({ command: configured, prefix: [] })

  const localPython = path.join(
    root,
    '.venv',
    platform === 'win32' ? 'Scripts' : 'bin',
    platform === 'win32' ? 'python.exe' : 'python',
  )
  if (existsSync(localPython)) candidates.push({ command: localPython, prefix: [] })
  if (platform === 'win32') candidates.push({ command: 'py', prefix: ['-3'] })
  candidates.push({ command: 'python', prefix: [] })

  for (const candidate of candidates) {
    if (probe(candidate.command, [...candidate.prefix, '-c', versionCheck])) {
      return {
        command: candidate.command,
        args: [...candidate.prefix, '-m', 'scripts.desktop_bridge'],
      }
    }
  }
  throw new Error('Python 3.9 or later is required. Install Python, then restart Expletive Deleted.')
}
