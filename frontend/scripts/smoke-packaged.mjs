import { access, mkdir, rm } from 'node:fs/promises'
import path from 'node:path'

const executable = process.env.PACKAGED_EXECUTABLE
  ? path.resolve(process.env.PACKAGED_EXECUTABLE)
  : path.resolve('release', 'win-unpacked', 'Expletive Deleted.exe')
await access(executable)

const temporaryDirectory = path.resolve('node_modules', '.tmp', 'playwright-packaged')
const appDataDirectory = path.join(temporaryDirectory, 'fresh-app-data')
await rm(appDataDirectory, { recursive: true, force: true })
await mkdir(temporaryDirectory, { recursive: true })
await mkdir(appDataDirectory, { recursive: true })
delete process.env.ELECTRON_RUN_AS_NODE

const { _electron: electron } = await import('playwright')
const packagedApp = await electron.launch({
  executablePath: executable,
  env: {
    ...process.env,
    CENSOR_PROJECT_ROOT: path.join(path.dirname(executable), 'resources', 'app-backend'),
    TMPDIR: temporaryDirectory,
    TMP: temporaryDirectory,
    TEMP: temporaryDirectory,
    LOCALAPPDATA: appDataDirectory,
  },
})

try {
  const window = await packagedApp.firstWindow()
  window.on('pageerror', (error) => console.error(`Renderer error: ${error.message}`))
  await window.waitForLoadState('domcontentloaded')
  await window.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()

  const freshSettings = await window.evaluate(() => window.expletiveDeleted.invoke('settings.get'))
  if (freshSettings.onboarding.completed) throw new Error('Fresh packaged settings should require onboarding')
  await window.evaluate((settings) => window.expletiveDeleted.invoke('settings.update', {
    settings: { ...settings, onboarding: { completed: true } },
  }), freshSettings)
  const launchUrl = new URL(window.url())
  launchUrl.searchParams.set('launch', 'completed')
  launchUrl.hash = '#/'
  await window.goto(launchUrl.toString())
  await window.getByRole('heading', { name: 'Queue', exact: true }).waitFor()
  await Promise.race([
    window.getByRole('heading', { name: 'Finish local setup', exact: true }).waitFor(),
    window.getByText('System ready', { exact: true }).waitFor(),
  ])

  const resourcesPath = await packagedApp.evaluate(() => process.resourcesPath)
  const backendRoot = path.join(resourcesPath, 'app-backend')
  await access(path.join(backendRoot, 'scripts', 'desktop_bridge.py'))
  await access(path.join(backendRoot, 'resources', 'profanity_censor_words.txt'))

  const { settings, legacyBridgePresent } = await window.evaluate(async () => ({
    settings: await window.expletiveDeleted.invoke('settings.get'),
    legacyBridgePresent: 'profanityCensor' in window,
  }))
  if (legacyBridgePresent) throw new Error('Obsolete preload bridge is still exposed')
  const installedResources = path.resolve(resourcesPath).toLowerCase()
  for (const [name, directory] of Object.entries(settings.directories)) {
    if (path.resolve(directory).toLowerCase().startsWith(installedResources)) {
      throw new Error(`Packaged settings directory ${name} is inside installed resources: ${directory}`)
    }
  }
  console.log(`Packaged Electron smoke passed: ${await window.title()}`)
} finally {
  await packagedApp.close()
}