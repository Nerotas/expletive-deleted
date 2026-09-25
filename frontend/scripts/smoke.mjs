import { access, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'

const electronTempDirectory = process.env.TEMP
const expectedAppVersion = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8')).version
const tempDirectory = path.join(process.cwd(), 'node_modules', '.tmp', 'playwright')
await mkdir(tempDirectory, { recursive: true })
const appDataDirectory = path.join(tempDirectory, 'fresh-app-data')
await rm(appDataDirectory, { recursive: true, force: true })
await mkdir(appDataDirectory, { recursive: true })
await access(path.join(process.cwd(), 'out', 'assets', 'expletive-deleted-icon.ico'))
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
    LOCALAPPDATA: appDataDirectory,
  },
})
try {
  const window = await app.firstWindow()
  const rendererErrors = []
  window.on('pageerror', (error) => rendererErrors.push(error.message))
  window.on('console', (message) => {
    if (message.type() === 'error') console.error(`Renderer console: ${message.text()}`)
  })
  await window.waitForLoadState('domcontentloaded')
  await window.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()

  const { appInfo, desktop, legacyBridgePresent } = await window.evaluate(async () => ({
    appInfo: await window.expletiveDeleted.getAppInfo(),
    desktop: window.expletiveDeleted.desktop,
    legacyBridgePresent: 'profanityCensor' in window,
  }))
  if (!desktop) throw new Error('Context-isolated desktop bridge was not exposed')
  if (legacyBridgePresent) throw new Error('Obsolete preload bridge is still exposed')
  if (appInfo.isPackaged) throw new Error('Development application reported itself as packaged')
  if (appInfo.version !== expectedAppVersion) {
    throw new Error(`Development application reported version ${appInfo.version}; expected ${expectedAppVersion}`)
  }
  if (await window.getByRole('dialog').count()) {
    throw new Error('Fresh onboarding began dependency retrieval without consent')
  }

  const results = path.join(process.cwd(), 'test-results')
  await mkdir(results, { recursive: true })
  await window.getByRole('button', { name: /Continue/ }).click()
  await window.getByRole('heading', { name: 'Prepare this computer', exact: true }).waitFor()
  await window.locator('.onboarding-page').evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished))
  })
  await window.screenshot({ path: path.join(results, 'desktop-onboarding.png'), fullPage: true })
  await window.evaluate(() => { document.documentElement.dataset.theme = 'dark' })
  await window.screenshot({ path: path.join(results, 'desktop-onboarding-dark.png'), fullPage: true })
  await window.evaluate(() => { document.documentElement.dataset.theme = 'light' })

  const freshSettings = await window.evaluate(() => window.expletiveDeleted.invoke('settings.get'))
  if (freshSettings.settings.onboarding.completed) throw new Error('Fresh settings should require onboarding')
  const directories = Object.fromEntries(['input', 'output', 'archive', 'transcripts'].map((name) => [name, path.join(appDataDirectory, 'media', name)]))
  await Promise.all(Object.values(directories).map((directory) => mkdir(directory, { recursive: true })))
  await writeFile(path.join(directories.input, 'Legacy example.mkv'), 'synthetic media')
  await writeFile(path.join(directories.transcripts, 'Legacy example-transcript.json'), '{}')
  await window.evaluate(({ settings, directories }) => window.expletiveDeleted.invoke('settings.update', {
    base: settings, settings: { ...settings.settings, directories, onboarding: { completed: true, last_step: "finish" } },
  }), { settings: freshSettings, directories })
  const launchUrl = new URL(window.url())
  launchUrl.searchParams.set('launch', 'completed')
  launchUrl.hash = '#/'
  await window.goto(launchUrl.toString())
  await window.getByRole('heading', { name: 'Queue', exact: true }).waitFor()

  const applicationMenuVisible = await app.evaluate(({ Menu }) => Menu.getApplicationMenu() !== null)
  if (applicationMenuVisible) throw new Error('Production Electron menu should be hidden')

  await Promise.race([
    window.getByRole('heading', { name: 'Local processing status', exact: true }).waitFor(),
    window.getByText('Processing ready', { exact: true }).waitFor(),
  ])

  await window.getByRole('link', { name: 'Settings', exact: true }).click()
  await window.getByRole('heading', { name: 'Settings', exact: true }).waitFor()
  await window.locator('.page').evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished))
  })
  const previousTheme = await window.evaluate(() => document.documentElement.dataset.theme)
  await window.evaluate(() => { document.documentElement.dataset.theme = 'light' })
  await window.screenshot({ path: path.join(results, 'desktop-settings.png'), fullPage: true })

  await window.evaluate(() => { document.documentElement.dataset.theme = 'dark' })
  const activeNavigationContrast = await window.getByRole('link', { name: 'Settings' }).evaluate(
    (element) => {
      const parseRgb = (value) => value.match(/\d+(?:\.\d+)?/g)?.slice(0, 3).map(Number) ?? []
      const luminance = (rgb) => {
        const channels = rgb.map((channel) => {
          const normalized = channel / 255
          return normalized <= 0.04045
            ? normalized / 12.92
            : ((normalized + 0.055) / 1.055) ** 2.4
        })
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
      }
      const styles = getComputedStyle(element)
      const foreground = luminance(parseRgb(styles.color))
      const background = luminance(parseRgb(styles.backgroundColor))
      return (Math.max(foreground, background) + 0.05)
        / (Math.min(foreground, background) + 0.05)
    },
  )
  if (activeNavigationContrast < 4.5) {
    throw new Error(`Dark active navigation contrast is ${activeNavigationContrast.toFixed(2)}:1`)
  }
  await window.screenshot({ path: path.join(results, 'desktop-settings-dark.png'), fullPage: true })
  await window.evaluate((theme) => {
    if (theme) document.documentElement.dataset.theme = theme
    else delete document.documentElement.dataset.theme
  }, previousTheme)

  await window.getByRole('link', { name: 'Dictionary', exact: true }).click()
  await window.getByRole('heading', { name: 'Dictionary', exact: true }).waitFor()
  const dictionaryReady = window.getByText('User dictionary', { exact: true })
  const dictionaryError = window.getByRole('alert')
  const dictionaryOutcome = await Promise.race([
    dictionaryReady.waitFor().then(() => 'ready'),
    dictionaryError.waitFor().then(() => 'error'),
  ])
  if (dictionaryOutcome === 'error') {
    throw new Error(`Dictionary failed to load: ${await dictionaryError.innerText()}`)
  }
  const exclusionsTab = window.getByRole('button', { name: /^Exclusions \(/ })
  await exclusionsTab.waitFor()
  if (await exclusionsTab.getAttribute('aria-pressed') !== 'true') {
    throw new Error('Dictionary did not default to exclusions')
  }
  await window.getByRole('button', { name: 'Censored words', exact: true }).click()
  const revealDialog = window.getByRole('dialog', { name: 'Reveal censored words?' })
  await revealDialog.waitFor()
  await revealDialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await revealDialog.waitFor({ state: 'detached' })
  if (await exclusionsTab.getAttribute('aria-pressed') !== 'true') {
    throw new Error('Cancelling the profanity warning changed the dictionary category')
  }
  await window.screenshot({ path: path.join(results, 'desktop-dictionary.png'), fullPage: true })

  await window.setViewportSize({ width: 1060, height: 720 })
  await window.evaluate(() => { document.documentElement.dataset.theme = 'dark' })
  await window.getByRole('button', { name: 'Restore defaults', exact: true }).click()
  const restoreDialog = window.getByRole('dialog', { name: 'Restore default dictionary?' })
  await restoreDialog.waitFor()
  await window.screenshot({ path: path.join(results, 'desktop-dictionary-dark.png'), fullPage: true })
  await restoreDialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await restoreDialog.waitFor({ state: 'detached' })
  await window.evaluate((theme) => {
    if (theme) document.documentElement.dataset.theme = theme
    else delete document.documentElement.dataset.theme
  }, previousTheme)

  await window.getByRole('link', { name: 'Queue', exact: true }).click()
  await window.getByRole('heading', { name: 'Queue', exact: true }).waitFor()

  await window.screenshot({ path: path.join(results, 'desktop-queue.png'), fullPage: true })
  const legacyRow = window.getByRole('row').filter({ hasText: 'Legacy example.mkv' })
  await legacyRow.getByText('Needs review', { exact: true }).waitFor()
  if (await legacyRow.getByRole('checkbox').isEnabled()) throw new Error('Legacy media must not enter bulk processing')
  if (await legacyRow.getByRole('button', { name: 'Play', exact: true }).count()) throw new Error('Legacy output identity must not be assumed')
  for (const width of [1060, 1440]) {
    await window.setViewportSize({ width, height: width === 1060 ? 720 : 900 })
    for (const theme of ['light', 'dark']) {
      await window.evaluate((theme) => { document.documentElement.dataset.theme = theme }, theme)
      await window.screenshot({ path: path.join(results, `desktop-identity-${width}-${theme}.png`), fullPage: true })
    }
  }
  if (rendererErrors.length) throw new Error(`Renderer errors: ${rendererErrors.join('; ')}`)
  console.log(`Electron smoke passed: ${await window.title()}`)
} finally {
  await app.close()
}
