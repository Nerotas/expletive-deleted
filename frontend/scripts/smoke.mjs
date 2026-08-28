import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const electronTempDirectory = process.env.TEMP
const tempDirectory = path.join(process.cwd(), 'node_modules', '.tmp', 'playwright')
await mkdir(tempDirectory, { recursive: true })
delete process.env.ELECTRON_RUN_AS_NODE
process.env.TMPDIR = tempDirectory
process.env.TMP = tempDirectory
process.env.TEMP = tempDirectory

const { _electron: electron } = await import('playwright')
const app = await electron.launch({
  args: ['.'],
  cwd: process.cwd(),
  env: {
    ...process.env,
    ...(electronTempDirectory
      ? { TEMP: electronTempDirectory, TMP: electronTempDirectory, TMPDIR: electronTempDirectory }
      : {}),
  },
})
try {
  const window = await app.firstWindow()
  window.on('pageerror', (error) => console.error(`Renderer error: ${error.message}`))
  window.on('console', (message) => {
    if (message.type() === 'error') console.error(`Renderer console: ${message.text()}`)
  })
  await window.waitForLoadState('domcontentloaded')
  await window.getByRole('heading', { name: 'Queue', exact: true }).waitFor()

  const desktop = await window.evaluate(() => window.profanityCensor.desktop)
  if (!desktop) throw new Error('Context-isolated desktop bridge was not exposed')

  await Promise.race([
    window.getByRole('heading', { name: 'Finish local setup', exact: true }).waitFor(),
    window.getByText('System ready', { exact: true }).waitFor(),
  ])

  await window.getByRole('link', { name: 'Settings', exact: true }).click()
  const results = path.join(process.cwd(), 'test-results')
  await mkdir(results, { recursive: true })
  await window.getByRole('heading', { name: 'Settings', exact: true }).waitFor()
  await window.screenshot({ path: path.join(results, 'desktop-settings.png'), fullPage: true })
  await window.getByRole('link', { name: 'Queue', exact: true }).click()
  await window.getByRole('heading', { name: 'Queue', exact: true }).waitFor()

  await window.screenshot({ path: path.join(results, 'desktop-queue.png'), fullPage: true })
  console.log(`Electron smoke passed: ${await window.title()}`)
} finally {
  await app.close()
}
