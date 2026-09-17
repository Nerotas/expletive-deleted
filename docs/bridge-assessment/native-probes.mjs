// Run from frontend/. OS file opening is intercepted; the web fixture is local.
import { createRequire } from 'node:module'
import { mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { createServer } from 'node:http'

const { _electron: electron } = createRequire(path.resolve('package.json'))('playwright')

delete process.env.ELECTRON_RUN_AS_NODE
const root = await mkdtemp(path.resolve('node_modules/.tmp/bridge-assessment-'))
const server = createServer((request, response) => response.end('<html><title>Untrusted audit page</title><body>Offline audit fixture</body></html>'))
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const app = await electron.launch({ args: ['.'], env: {
  ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(CENSOR_|PYTHON|ELECTRON_RENDERER_URL)/i.test(key))),
  CENSOR_APP_DATA_DIR: path.join(root, 'data'), CENSOR_PYTHON: path.resolve('../.venv/Scripts/python.exe'),
}})
try {
  const page = await app.firstWindow()
  await page.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()
  const preferences = await app.evaluate(({ BrowserWindow, shell }) => {
    globalThis.auditOpenPaths = []
    shell.openPath = async value => { globalThis.auditOpenPaths.push(value); return '' }
    const prefs = BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences()
    return { sandbox: prefs.sandbox, contextIsolation: prefs.contextIsolation, nodeIntegration: prefs.nodeIntegration }
  })
  // Observe the native call without launching any file or program.
  await page.evaluate(() => window.expletiveDeleted.openFile('C:\\Windows\\System32\\cmd.exe'))
  const openPaths = await app.evaluate(() => globalThis.auditOpenPaths)
  const csp = await page.locator('meta[http-equiv="Content-Security-Policy"]').count()
  await Promise.all([page.waitForURL(`${origin}/`), page.evaluate(url => { location.href = url }, origin)])
  const foreignAccess = await page.evaluate(async () => {
    const settings = await window.expletiveDeleted.invoke('settings.get')
    return { bridgePresent: Boolean(window.expletiveDeleted), settingsReadable: Boolean(settings.directories) }
  })
  console.log(JSON.stringify({ preferences, cspMetaCount: csp, interceptedOpenPaths: openPaths, foreignOriginAccess: foreignAccess }))
} finally {
  await app.close()
  server.close()
}
