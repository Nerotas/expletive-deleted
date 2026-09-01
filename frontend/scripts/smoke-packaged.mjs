import { access, mkdir } from 'node:fs/promises'
import path from 'node:path'

const executable = process.env.PACKAGED_EXECUTABLE
  ? path.resolve(process.env.PACKAGED_EXECUTABLE)
  : path.resolve('release', 'win-unpacked', 'Expletive Deleted.exe')
await access(executable)

const temporaryDirectory = path.resolve('node_modules', '.tmp', 'playwright-packaged')
await mkdir(temporaryDirectory, { recursive: true })
delete process.env.ELECTRON_RUN_AS_NODE

const { _electron: electron } = await import('playwright')
const packagedApp = await electron.launch({
  executablePath: executable,
  env: {
    ...process.env,
    TMPDIR: temporaryDirectory,
    TMP: temporaryDirectory,
    TEMP: temporaryDirectory,
  },
})

try {
  const window = await packagedApp.firstWindow()
  window.on('pageerror', (error) => console.error(`Renderer error: ${error.message}`))
  await window.waitForLoadState('domcontentloaded')
  await window.getByRole('heading', { name: 'Queue', exact: true }).waitFor()
  await Promise.race([
    window.getByRole('heading', { name: 'Finish local setup', exact: true }).waitFor(),
    window.getByText('System ready', { exact: true }).waitFor(),
  ])

  const resourcesPath = await packagedApp.evaluate(() => process.resourcesPath)
  const backendRoot = path.join(resourcesPath, 'app-backend')
  await access(path.join(backendRoot, 'scripts', 'desktop_bridge.py'))
  await access(path.join(backendRoot, 'resources', 'profanity_censor_words.txt'))
  console.log(`Packaged Electron smoke passed: ${await window.title()}`)
} finally {
  await packagedApp.close()
}