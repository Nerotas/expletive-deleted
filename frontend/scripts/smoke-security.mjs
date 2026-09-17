import assert from 'node:assert/strict'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { assertRendererSecurity } from './security-checks.mjs'

const temporaryRoot = path.resolve('node_modules', '.tmp')
await mkdir(temporaryRoot, { recursive: true })
const temporaryDirectory = await mkdtemp(path.join(temporaryRoot, 'security-'))
delete process.env.ELECTRON_RUN_AS_NODE
const cleanEnvironment = Object.fromEntries(Object.entries(process.env)
  .filter(([key]) => !/^(CENSOR_|PYTHON|ELECTRON_RENDERER_URL)/i.test(key)))
const { _electron: electron } = await import('playwright')

// Use the repository's actual Vite configuration, including the React refresh preamble.
for (const development of [false, true]) {
  let server
  let app
  try {
    if (development) {
      const { resolveConfig } = await import('electron-vite')
      const { createServer } = await import('vite')
      const resolved = await resolveConfig({}, 'serve')
      server = await createServer({ ...resolved.config.renderer, configFile: false })
      await server.listen()
    }
    const appDataDirectory = path.join(temporaryDirectory, development ? 'development' : 'production')
    await mkdir(appDataDirectory, { recursive: true })
    console.log(`Launching security smoke: ${development ? 'development' : 'production'}`)
    app = await electron.launch({ args: ['.'], cwd: process.cwd(), env: {
      ...cleanEnvironment,
      LOCALAPPDATA: appDataDirectory,
      CENSOR_APP_DATA_DIR: path.join(appDataDirectory, 'ExpletiveDeleted'),
      ...(development ? { ELECTRON_RENDERER_URL: server.resolvedUrls.local[0] } : {}),
    } })
    const page = await app.firstWindow()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()
    console.log('Sandboxed app started; checking native file paths')
    // webUtils must still resolve native dropped/selected files under sandboxing.
    const fixturePath = path.join(appDataDirectory, 'selected-file.txt')
    await writeFile(fixturePath, 'Synthetic security fixture')
    await page.evaluate(() => {
      const input = document.createElement('input')
      input.type = 'file'
      input.id = 'security-file'
      document.body.append(input)
    })
    await page.locator('#security-file').setInputFiles(fixturePath)
    assert.equal(await page.locator('#security-file').evaluate((input) => window.expletiveDeleted.getPathForFile(input.files[0])), fixturePath)
    if (development) {
      // A server-sent update proves the restricted WebSocket connection supports HMR.
      await page.waitForFunction(() => typeof window.$RefreshReg$ === 'function')
      await new Promise((resolve, reject) => {
        if (server.ws.clients.size) resolve()
        else {
          const timeout = setTimeout(() => reject(new Error('Vite HMR WebSocket did not connect')), 5000)
          server.ws.on('connection', () => { clearTimeout(timeout); resolve() })
        }
      })
      const reloaded = page.waitForEvent('domcontentloaded')
      server.ws.send({ type: 'full-reload' })
      await reloaded
      await page.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()
    }
    await assertRendererSecurity(app, page, { development })
    assert.deepEqual(errors, [])
  } finally {
    await app?.close()
    await server?.close()
  }
}
