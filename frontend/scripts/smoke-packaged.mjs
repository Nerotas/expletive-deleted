import { access, mkdir, rm } from 'node:fs/promises'
import path from 'node:path'

const executable = process.env.PACKAGED_EXECUTABLE
  ? path.resolve(process.env.PACKAGED_EXECUTABLE)
  : path.resolve('release', 'win-unpacked', 'Expletive Deleted.exe')
const requireBundledRuntime = process.argv.includes('--require-bundled-runtime') || process.env.REQUIRE_BUNDLED_RUNTIME === '1'
await access(executable)

const temporaryDirectory = path.resolve('node_modules', '.tmp', 'playwright-packaged')
const appDataDirectory = path.join(temporaryDirectory, 'fresh-app-data')
await rm(appDataDirectory, { recursive: true, force: true })
await mkdir(temporaryDirectory, { recursive: true })
await mkdir(appDataDirectory, { recursive: true })
delete process.env.ELECTRON_RUN_AS_NODE
const cleanSystemPath = path.join(process.env.SystemRoot ?? 'C:\\Windows', 'System32')

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
    // Release smoke must prove that no ambient tools satisfy readiness. The
    // development package intentionally relies on the CI-provided Python.
    ...(requireBundledRuntime ? { PATH: cleanSystemPath } : {}),
  },
})

try {
  const window = await packagedApp.firstWindow()
  window.on('pageerror', (error) => console.error(`Renderer error: ${error.message}`))
  await window.waitForLoadState('domcontentloaded')
  const startupOutcome = await Promise.race([
    window.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor().then(() => 'ready'),
    window.getByRole('heading', { name: 'Repair Expletive Deleted', exact: true }).waitFor().then(() => 'repair'),
  ])
  if (startupOutcome === 'repair') {
    const detail = await window.locator('.backend-setup-detail').textContent().catch(() => null)
    throw new Error(`Packaged backend did not start${detail ? `: ${detail}` : '.'}`)
  }

  if (requireBundledRuntime) {
    await window.getByRole('button', { name: /Continue/ }).click()
    await window.getByRole('heading', { name: 'Prepare this computer', exact: true }).waitFor()
    await window.getByText('Transcription packages', { exact: true }).waitFor()
    await window.getByText('FFmpeg and FFprobe', { exact: true }).waitFor()
    await window.getByText('YouTube tools', { exact: true }).waitFor()
  }

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

  const resourcesPath = await packagedApp.evaluate(() => process.resourcesPath)
  const backendRoot = path.join(resourcesPath, 'app-backend')
  await access(path.join(backendRoot, 'scripts', 'desktop_bridge.py'))
  await access(path.join(backendRoot, 'resources', 'profanity_censor_words.txt'))

  const runtimeRoot = path.join(resourcesPath, 'app-runtime')
  if (requireBundledRuntime) {
    await Promise.all([
      access(path.join(runtimeRoot, 'python', 'python.exe')),
    ])
    for (const excludedPath of [
      path.join(runtimeRoot, 'ffmpeg'),
      path.join(runtimeRoot, 'yt-dlp'),
      path.join(runtimeRoot, 'deno'),
      path.join(runtimeRoot, 'ffmpeg-build.json'),
      path.join(runtimeRoot, 'ffmpeg-source.zip'),
    ]) {
      await access(excludedPath)
        .then(() => { throw new Error(`Python-only package unexpectedly included ${excludedPath}`) })
        .catch((error) => {
          if (error instanceof Error && error.message.startsWith('Python-only package unexpectedly')) throw error
        })
    }
  }

  const { settings, capabilities, legacyBridgePresent } = await window.evaluate(async () => ({
    settings: await window.expletiveDeleted.invoke('settings.get'),
    capabilities: await window.expletiveDeleted.invoke('capabilities.get'),
    legacyBridgePresent: 'profanityCensor' in window,
  }))
  if (legacyBridgePresent) throw new Error('Obsolete preload bridge is still exposed')
  if (requireBundledRuntime) {
    if (capabilities.app_runtime !== 'ready' || capabilities.app_runtime_source !== 'bundled') {
      throw new Error('Clean packaged app did not verify its private runtime.')
    }
    if (capabilities.speech_model === 'ready' || capabilities.processing_ready === true) {
      throw new Error('Clean packaged app unexpectedly included a speech model.')
    }
    if (capabilities.whisper === true || capabilities.ffmpeg === true || capabilities.ffprobe === true) {
      throw new Error('Clean packaged app unexpectedly reported bundled processing packages or media tools.')
    }
    if (capabilities.ytdlp === true && capabilities.js_runtime !== true) {
      throw new Error('Packaged bridge reported an inconsistent YouTube setup state.')
    }
    if (capabilities.ytdlp === true || capabilities.js_runtime === true) {
      throw new Error('Setup-first package unexpectedly reported bundled YouTube tooling.')
    }
  }
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
