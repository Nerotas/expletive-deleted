import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'

export type BackendRuntime = {
  root: string
  command: string
  args: string[]
}

export function backendEnvironment(
  environment: NodeJS.ProcessEnv = process.env,
): NodeJS.ProcessEnv {
  return { ...environment, CENSOR_PROJECT_ROOT: '' }
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
): Omit<BackendRuntime, 'root'> {
  const configured = environment.CENSOR_PYTHON?.trim()
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

  const versionCheck = 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'
  for (const candidate of candidates) {
    const check = spawnSync(candidate.command, [...candidate.prefix, '-c', versionCheck], {
      encoding: 'utf8',
      windowsHide: true,
      timeout: 10_000,
    })
    if (check.status === 0) {
      return {
        command: candidate.command,
        args: [...candidate.prefix, '-m', 'scripts.desktop_bridge'],
      }
    }
  }
  throw new Error('Python 3.9 or later is required. Install Python, then restart Expletive Deleted.')
}