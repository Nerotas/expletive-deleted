import { app, BrowserWindow, dialog, ipcMain, Menu, shell } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync, statSync } from 'node:fs'
import path from 'node:path'
import { backendEnvironment, findBackendRoot, findPythonRuntime, requireBundledRuntime } from './backend-runtime.js'
import { BridgeTransport, transportError, type RequestOptions } from './bridge-transport.js'
import { stopBridge } from './bridge-shutdown.js'
import { secureRendererWindow, trustedIpcHandlers, type TrustedRenderer } from './ipc-security.js'
import { createRendererPolicy } from './renderer-policy.js'
import { nativeFileOperations, assertRendererMethod } from './native-files.js'
import { respond } from './ipc-response.js'
import { claimDesktopInstance } from './single-instance.js'

let trustedRenderer: TrustedRenderer | undefined
let bridge: ChildProcessWithoutNullStreams | undefined
let transport: BridgeTransport | undefined
let generation = 0
let bridgeFailure: string | undefined
let shuttingDown = false
let shutdownComplete = false
const APPLICATION_ID = 'com.expletive-deleted.desktop'
const APPLICATION_ICON = 'expletive-deleted-icon.ico'
// Keep development and packaged launches on the same per-user ownership key.
const applicationData = process.env.CENSOR_APP_DATA_DIR?.trim()
  || path.join(process.env.LOCALAPPDATA || app.getPath('appData'), 'ExpletiveDeleted')
app.setPath('userData', path.resolve(applicationData, 'desktop'))
const desktopInstance = claimDesktopInstance(app)
const rendererPolicy = createRendererPolicy(path.join(__dirname, '../renderer/index.html'), app.isPackaged, process.env.ELECTRON_RENDERER_URL)
const developmentLogging = Boolean(rendererPolicy.development)

function logDevelopmentError(context: string, error: unknown): void {
  if (developmentLogging) console.error(`[Expletive Deleted] ${context}`, error)
}

function resolveApplicationIcon(): string | undefined {
  const candidates = [
    path.join(process.resourcesPath, 'assets', APPLICATION_ICON),
    path.join(app.getAppPath(), 'assets', APPLICATION_ICON),
    path.join(app.getAppPath(), 'out', 'assets', APPLICATION_ICON),
    path.join(app.getAppPath(), 'src', 'assets', APPLICATION_ICON),
  ]
  return candidates.find((candidate) => existsSync(candidate))
}

function startBridge(): void {
  let root: string
  let runtime: ReturnType<typeof findPythonRuntime>
  let bundledRuntime: ReturnType<typeof requireBundledRuntime>
  try {
    bundledRuntime = app.isPackaged
      ? requireBundledRuntime(process.resourcesPath, process.platform)
      : {}
    root = findBackendRoot({
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      appPath: app.getAppPath(),
      cwd: process.cwd(),
      moduleDirectory: __dirname,
    })
    runtime = findPythonRuntime(root, process.platform, process.env, bundledRuntime.python)
  } catch (error) {
    bridgeFailure = error instanceof Error ? error.message : String(error)
    return
  }
  bridge = spawn(runtime.command, runtime.args, {
    cwd: root,
    env: backendEnvironment(process.env, bundledRuntime),
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  let stderr = ''
  bridge.stderr.on('data', (chunk: Buffer) => {
    const message = chunk.toString()
    stderr += message
    logDevelopmentError('Python bridge stderr:', message.trim())
  })
  const child = bridge
  transport = new BridgeTransport(++generation, (line, done) => child.stdin.write(line, done), (state) => {
    const window = trustedRenderer?.window
    if (window && !window.isDestroyed() && rendererPolicy.allows(window.webContents.getURL())) {
      window.webContents.send('expletive-deleted:backend-state', state)
    }
  })
  const currentTransport = transport
  child.stdout.on('data', (chunk: Buffer) => currentTransport.receive(chunk))
  child.stdout.on('end', () => currentTransport.stop('unavailable'))
  child.stdin.on('error', () => currentTransport.stop('unavailable'))
  bridge.on('error', (error) => {
    bridgeFailure = `Could not start the local processing service: ${error.message}`
    logDevelopmentError('Python bridge failed to start:', error)
    currentTransport.stop('unavailable')
  })
  bridge.on('exit', (code) => {
    bridge = undefined
    bridgeFailure = stderr.trim() || `The local processing service stopped unexpectedly${code === null ? '' : ` (exit code ${code})`}.`
    logDevelopmentError('Python bridge exited:', bridgeFailure)
    currentTransport.stop('exited')
  })
}

function invoke(method: string, params?: Record<string, unknown>, options?: RequestOptions): Promise<unknown> {
  if (shuttingDown) return Promise.reject(transportError('backend_exited', 'The desktop application is closing.'))
  if (!transport) return Promise.reject(transportError('backend_unavailable', bridgeFailure ?? 'The local processing service is unavailable.'))
  return transport.request(method, params, options)
}

function outputDirectory(settings: unknown): string {
  if (!settings || typeof settings !== 'object') throw new Error('Could not read the configured transcode folder.')
  const directories = (settings as { settings?: { directories?: unknown } }).settings?.directories
  if (!directories || typeof directories !== 'object') throw new Error('Could not read the configured transcode folder.')
  const output = (directories as { output?: unknown }).output
  if (typeof output !== 'string' || !output.trim()) throw new Error('The configured transcode folder is unavailable.')
  try {
    if (!statSync(output).isDirectory()) throw new Error('not a directory')
  } catch {
    throw new Error('The configured transcode folder is unavailable.')
  }
  return output
}

function createWindow(): void {
  const icon = resolveApplicationIcon()
  const browserWindow = new BrowserWindow({
    width: 1440, height: 940, minWidth: 1060, minHeight: 720, show: false,
    ...(icon ? { icon } : {}),
    webPreferences: { preload: path.join(__dirname, '../preload/preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  trustedRenderer = secureRendererWindow(browserWindow, rendererPolicy)
  browserWindow.once('ready-to-show', () => {
    browserWindow.show()
    desktopInstance.windowReady(browserWindow)
  })
  browserWindow.on('closed', () => {
    trustedRenderer = undefined
    void invoke('native.release_all').catch(() => {})
  })
  void browserWindow.loadURL(rendererPolicy.entryUrl)
}

if (process.platform === 'win32') app.setAppUserModelId(APPLICATION_ID)

if (desktopInstance.ownsInstance) app.whenReady().then(() => {
  if (!rendererPolicy.development) Menu.setApplicationMenu(null)
  startBridge()
  const handle = trustedIpcHandlers(ipcMain, () => trustedRenderer)
  const nativeFiles = nativeFileOperations(invoke, dialog, shell)
  handle('expletive-deleted:invoke', (_request, method: string, params?: Record<string, unknown>, options?: RequestOptions) => respond(async () => {
    assertRendererMethod(method)
    return invoke(method, params, options)
  }))
  handle('expletive-deleted:backend-state', () => transport?.snapshot ?? { generation, status: 'unavailable' })
  handle('expletive-deleted:restart', () => {
    // Relaunch is a user action. before-quit still applies bounded worker shutdown.
    app.relaunch()
    app.quit()
  })
  handle('expletive-deleted:select-directory', async ({ window }, defaultPath?: string) => {
    const result = await dialog.showOpenDialog(window, { defaultPath, properties: ['openDirectory', 'createDirectory'] })
    return result.canceled ? undefined : result.filePaths[0]
  })
  handle('expletive-deleted:select-file', async ({ window }, defaultPath?: string) => {
    const result = await dialog.showOpenDialog(window, {
      defaultPath,
      properties: ['openFile'],
      filters: process.platform === 'win32'
        ? [{ name: 'FFmpeg executable', extensions: ['exe'] }]
        : undefined,
    })
    return result.canceled ? undefined : result.filePaths[0]
  })
  handle('expletive-deleted:import-dictionary', (request) => respond(() => nativeFiles.importDictionary(request)))
  handle('expletive-deleted:export-dictionary', (request) => respond(() => nativeFiles.exportDictionary(request)))
  handle('expletive-deleted:open-external', async (_request, value: string) => {
    const url = new URL(value)
    if (url.protocol !== 'https:') throw new Error('Only secure project links can be opened')
    await shell.openExternal(url.toString())
  })
  handle('expletive-deleted:open-transcode-folder', async ({ assertCurrent }) => {
    const folderPath = outputDirectory(await invoke('settings.get'))
    assertCurrent()
    const error = await shell.openPath(folderPath)
    if (error) throw new Error(`Could not open the transcode folder: ${error}`)
  })
  handle('expletive-deleted:open-output', (request, source: string) => respond(() => nativeFiles.openOutput(request, source)))
  createWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', (event) => {
  if (shutdownComplete || !bridge) return
  event.preventDefault()
  if (shuttingDown) return
  shuttingDown = true
  transport?.stop('exited')
  void stopBridge(bridge).finally(() => {
    shutdownComplete = true
    app.quit()
  })
})
