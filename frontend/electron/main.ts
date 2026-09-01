import { app, BrowserWindow, dialog, ipcMain, Menu, shell, type IpcMainInvokeEvent } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { findBackendRoot, findPythonRuntime } from './backend-runtime.js'

type BridgeResponse = { id: number; ok: true; result: unknown } | { id: number; ok: false; error: { message?: string } }

let window: BrowserWindow | undefined
let bridge: ChildProcessWithoutNullStreams | undefined
let requestId = 0
let bridgeFailure: string | undefined
const pending = new Map<number, { resolve: (value: unknown) => void; reject: (reason: Error) => void }>()
const APPLICATION_ID = 'com.profanity-censor.desktop'
const APPLICATION_ICON = 'profanity-censor-icon.ico'

function resolveApplicationIcon(): string | undefined {
  const candidates = [
    path.join(process.resourcesPath, 'assets', APPLICATION_ICON),
    path.join(app.getAppPath(), 'assets', APPLICATION_ICON),
    path.join(app.getAppPath(), 'out', 'assets', APPLICATION_ICON),
    path.join(app.getAppPath(), 'src', 'assets', APPLICATION_ICON),
  ]
  return candidates.find((candidate) => existsSync(candidate))
}

function rejectPending(message: string): void {
  for (const request of pending.values()) request.reject(new Error(message))
  pending.clear()
}

function startBridge(): void {
  let root: string
  let runtime: ReturnType<typeof findPythonRuntime>
  try {
    root = findBackendRoot({
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      appPath: app.getAppPath(),
      cwd: process.cwd(),
      moduleDirectory: __dirname,
    })
    runtime = findPythonRuntime(root, process.platform)
  } catch (error) {
    bridgeFailure = error instanceof Error ? error.message : String(error)
    return
  }
  bridge = spawn(runtime.command, runtime.args, {
    cwd: root,
    env: { ...process.env, CENSOR_PROJECT_ROOT: root },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  let stderr = ''
  bridge.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString() })
  let buffer = ''
  bridge.stdout.on('data', (chunk: Buffer) => {
    buffer += chunk.toString()
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      try {
        const response = JSON.parse(line) as BridgeResponse
        const request = pending.get(response.id)
        if (!request) continue
        pending.delete(response.id)
        if (response.ok) request.resolve(response.result)
        else request.reject(new Error(response.error.message ?? 'The local processing service rejected the request.'))
      } catch { /* ignore malformed private protocol output */ }
    }
  })
  bridge.on('error', (error) => {
    bridgeFailure = `Could not start the local processing service: ${error.message}`
    rejectPending(bridgeFailure)
  })
  bridge.on('exit', (code) => {
    bridge = undefined
    bridgeFailure = stderr.trim() || `The local processing service stopped unexpectedly${code === null ? '' : ` (exit code ${code})`}.`
    rejectPending(bridgeFailure)
  })
}

function invoke(method: string, params?: Record<string, unknown>): Promise<unknown> {
  if (!bridge?.stdin.writable) return Promise.reject(new Error(bridgeFailure ?? 'The local processing service is unavailable. Restart the desktop application.'))
  const id = ++requestId
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    bridge!.stdin.write(`${JSON.stringify({ id, method, ...(params ? { params } : {}) })}\n`, (error) => {
      if (!error) return
      pending.delete(id)
      reject(new Error(`Could not contact the local processing service: ${error.message}`))
    })
  })
}

function createWindow(): void {
  const icon = resolveApplicationIcon()
  const browserWindow = new BrowserWindow({
    width: 1440, height: 940, minWidth: 1060, minHeight: 720, show: false,
    ...(icon ? { icon } : {}),
    webPreferences: { preload: path.join(__dirname, '../preload/preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: false },
  })
  window = browserWindow
  browserWindow.once('ready-to-show', () => browserWindow.show())
  browserWindow.on('closed', () => { window = undefined })
  if (process.env.ELECTRON_RENDERER_URL) void browserWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  else void browserWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
}

if (process.platform === 'win32') app.setAppUserModelId(APPLICATION_ID)

app.whenReady().then(() => {
  if (!process.env.ELECTRON_RENDERER_URL) Menu.setApplicationMenu(null)
  startBridge()
  ipcMain.handle('profanity-censor:invoke', (_event: IpcMainInvokeEvent, method: string, params?: Record<string, unknown>) => invoke(method, params))
  ipcMain.handle('profanity-censor:select-directory', async (_event: IpcMainInvokeEvent, defaultPath?: string) => {
    const result = await dialog.showOpenDialog(window!, { defaultPath, properties: ['openDirectory', 'createDirectory'] })
    return result.canceled ? undefined : result.filePaths[0]
  })
  ipcMain.handle('profanity-censor:select-file', async (_event: IpcMainInvokeEvent, defaultPath?: string) => {
    const result = await dialog.showOpenDialog(window!, {
      defaultPath,
      properties: ['openFile'],
      filters: process.platform === 'win32'
        ? [{ name: 'FFmpeg executable', extensions: ['exe'] }]
        : undefined,
    })
    return result.canceled ? undefined : result.filePaths[0]
  })
  ipcMain.handle('profanity-censor:select-dictionary-import', async () => {
    const result = await dialog.showOpenDialog(window!, {
      properties: ['openFile'],
      filters: [{ name: 'Expletive Deleted dictionary', extensions: ['json'] }],
    })
    return result.canceled ? undefined : result.filePaths[0]
  })
  ipcMain.handle('profanity-censor:select-dictionary-export', async () => {
    const result = await dialog.showSaveDialog(window!, {
      defaultPath: 'expletive-deleted-dictionary.json',
      filters: [{ name: 'Expletive Deleted dictionary', extensions: ['json'] }],
    })
    return result.canceled ? undefined : result.filePath
  })
  ipcMain.handle('profanity-censor:open-external', async (_event: IpcMainInvokeEvent, value: string) => {
    const url = new URL(value)
    if (url.protocol !== 'https:') throw new Error('Only secure project links can be opened')
    await shell.openExternal(url.toString())
  })
  createWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', () => { bridge?.kill(); bridge = undefined; rejectPending('The desktop application is closing.') })
