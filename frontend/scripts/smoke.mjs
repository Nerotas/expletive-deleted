import { access, mkdir } from 'node:fs/promises'
import path from 'node:path'

const electronTempDirectory = process.env.TEMP
const tempDirectory = path.join(process.cwd(), 'node_modules', '.tmp', 'playwright')
await mkdir(tempDirectory, { recursive: true })
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

  const { desktop, legacyBridgePresent } = await window.evaluate(() => ({
    desktop: window.expletiveDeleted.desktop,
    legacyBridgePresent: 'profanityCensor' in window,
  }))
  if (!desktop) throw new Error('Context-isolated desktop bridge was not exposed')
  if (legacyBridgePresent) throw new Error('Obsolete preload bridge is still exposed')

  const applicationMenuVisible = await app.evaluate(({ Menu }) => Menu.getApplicationMenu() !== null)
  if (applicationMenuVisible) throw new Error('Production Electron menu should be hidden')

  await Promise.race([
    window.getByRole('heading', { name: 'Finish local setup', exact: true }).waitFor(),
    window.getByText('System ready', { exact: true }).waitFor(),
  ])

  await window.getByRole('link', { name: 'Settings', exact: true }).click()
  const results = path.join(process.cwd(), 'test-results')
  await mkdir(results, { recursive: true })
  await window.getByRole('heading', { name: 'Settings', exact: true }).waitFor()
  await window.screenshot({ path: path.join(results, 'desktop-settings.png'), fullPage: true })

  const previousTheme = await window.evaluate(() => document.documentElement.dataset.theme)
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
  console.log(`Electron smoke passed: ${await window.title()}`)
} finally {
  await app.close()
}
