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
  ffmpeg?: string
  ffprobe?: string
  ytdlp?: string
}

export function findBundledRuntime(
  resourcesPath: string,
  platform: NodeJS.Platform,
  exists: (candidate: string) => boolean = existsSync,
): BundledRuntimePaths {
  const executableName = platform === 'win32' ? 'python.exe' : 'python'
  const ffmpegName = platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg'
  const ffprobeName = platform === 'win32' ? 'ffprobe.exe' : 'ffprobe'
  const ytdlpName = platform === 'win32' ? 'yt-dlp.exe' : 'yt-dlp'
  const runtimeRoot = path.join(resourcesPath, 'app-runtime')
  const python = path.join(runtimeRoot, 'python', executableName)
  const ffmpeg = path.join(runtimeRoot, 'ffmpeg', ffmpegName)
  const ffprobe = path.join(runtimeRoot, 'ffmpeg', ffprobeName)
  const ytdlp = path.join(runtimeRoot, 'yt-dlp', ytdlpName)

  if (!exists(python) || !exists(ffmpeg) || !exists(ffprobe) || !exists(ytdlp)) return {}
  return { python, ffmpeg, ffprobe, ytdlp }
}

export function requireBundledRuntime(
  resourcesPath: string,
  platform: NodeJS.Platform,
  exists: (candidate: string) => boolean = existsSync,
): BundledRuntimePaths {
  const manifest = path.join(resourcesPath, 'app-runtime', 'runtime-manifest.json')
  if (!exists(manifest)) return {}
  const runtime = findBundledRuntime(resourcesPath, platform, exists)
  if (runtime.python && runtime.ffmpeg && runtime.ffprobe && runtime.ytdlp) return runtime
  throw new Error('The installed local processing runtime is incomplete. Reinstall Expletive Deleted.')
}

export function backendEnvironment(
  environment: NodeJS.ProcessEnv = process.env,
  bundledRuntime: BundledRuntimePaths = {},
): NodeJS.ProcessEnv {
  const localAppData = environment.LOCALAPPDATA?.trim()
  const bundledFfmpegDirectory = bundledRuntime.ffmpeg
    ? path.dirname(bundledRuntime.ffmpeg)
    : undefined
  const completeBundledRuntime = Boolean(
    bundledRuntime.python && bundledRuntime.ffmpeg && bundledRuntime.ffprobe && bundledRuntime.ytdlp,
  )
  const currentPath = environment.PATH ?? ''

  return {
    ...environment,
    CENSOR_PROJECT_ROOT: '',
    ...(localAppData ? { CENSOR_APP_DATA_DIR: path.join(localAppData, 'ExpletiveDeleted') } : {}),
    ...(completeBundledRuntime ? { CENSOR_BUNDLED_RUNTIME: '1' } : {}),
    ...(bundledRuntime.ffmpeg ? { CENSOR_FFMPEG: bundledRuntime.ffmpeg } : {}),
    ...(bundledRuntime.ffprobe ? { CENSOR_FFPROBE: bundledRuntime.ffprobe } : {}),
    ...(bundledRuntime.ytdlp ? { CENSOR_YTDLP: bundledRuntime.ytdlp } : {}),
    ...(bundledFfmpegDirectory
      ? { PATH: currentPath ? bundledFfmpegDirectory + path.delimiter + currentPath : bundledFfmpegDirectory }
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
): Omit<BackendRuntime, 'root'> {
  const configured = environment.CENSOR_PYTHON?.trim()
  const candidates: Array<{ command: string; prefix: string[] }> = []
  if (bundledPython && existsSync(bundledPython)) candidates.push({ command: bundledPython, prefix: [] })
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
