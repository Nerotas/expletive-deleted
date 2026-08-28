import { app, BrowserWindow, dialog, ipcMain, type IpcMainInvokeEvent } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'

type BridgeResponse = { id: number; ok: true; result: unknown } | { id: number; ok: false; error: { message?: string } }

let window: BrowserWindow | undefined
let bridge: ChildProcessWithoutNullStreams | undefined
let requestId = 0
const pending = new Map<number, { resolve: (value: unknown) => void; reject: (reason: Error) => void }>()

function rejectPending(message: string): void {
  for (const request of pending.values()) request.reject(new Error(message))
  pending.clear()
}

function startBridge(): void {
  const root = path.resolve(app.getAppPath(), '..')
  const venvPython = path.join(root, '.venv', 'Scripts', process.platform === 'win32' ? 'python.exe' : 'python')
  bridge = spawn(existsSync(venvPython) ? venvPython : 'python', ['scripts/desktop_bridge.py'], {
    cwd: root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  })
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
  bridge.on('error', (error) => rejectPending(`Could not start the local processing service: ${error.message}`))
  bridge.on('exit', (code) => { bridge = undefined; rejectPending(`The local processing service stopped unexpectedly${code === null ? '' : ` (exit code ${code})`}.`) })
}

function invoke(method: string, params?: Record<string, unknown>): Promise<unknown> {
  if (!bridge?.stdin.writable) return Promise.reject(new Error('The local processing service is unavailable. Restart the desktop application.'))
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
  const browserWindow = new BrowserWindow({
    width: 1440, height: 940, minWidth: 1060, minHeight: 720, show: false,
    webPreferences: { preload: path.join(__dirname, '../preload/preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: false },
  })
  window = browserWindow
  browserWindow.once('ready-to-show', () => browserWindow.show())
  browserWindow.on('closed', () => { window = undefined })
  if (process.env.ELECTRON_RENDERER_URL) void browserWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  else void browserWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
}

app.whenReady().then(() => {
  startBridge()
  ipcMain.handle('profanity-censor:invoke', (_event: IpcMainInvokeEvent, method: string, params?: Record<string, unknown>) => invoke(method, params))
  ipcMain.handle('profanity-censor:select-directory', async (_event: IpcMainInvokeEvent, defaultPath?: string) => {
    const result = await dialog.showOpenDialog(window!, { defaultPath, properties: ['openDirectory', 'createDirectory'] })
    return result.canceled ? undefined : result.filePaths[0]
  })
  createWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', () => { bridge?.kill(); bridge = undefined; rejectPending('The desktop application is closing.') })
