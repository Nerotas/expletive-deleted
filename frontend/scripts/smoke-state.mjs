import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { spawn, execFileSync, execFile } from 'node:child_process'
import { createRequire } from 'node:module'
import { promisify } from 'node:util'
import path from 'node:path'
import { _electron as electron } from 'playwright'

const require = createRequire(import.meta.url)
const executable = require('electron')
const repository = path.resolve('..')
const localPython = path.join(repository, '.venv/Scripts/python.exe')
const python = process.env.CENSOR_PYTHON || (existsSync(localPython) ? localPython
  : execFileSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).trim())
await mkdir('node_modules/.tmp', { recursive: true })
const root = await mkdtemp(path.resolve('node_modules/.tmp/state-'))
const harness = path.join(root, 'harness.cjs')
const events = path.join(root, 'lifecycle.jsonl')
// Instrument the actual main entrypoint, without production test switches. Hold
// only its startup callback so a real second launch arrives before any window.
await writeFile(harness, `
const { app } = require('electron');
const fs = require('node:fs');
const cp = require('node:child_process');
const log = (event) => fs.appendFileSync(${JSON.stringify(events)}, JSON.stringify({ ...event, owner: process.pid }) + '\\n');
const originalSpawn = cp.spawn;
cp.spawn = (...args) => {
  if (args[1]?.includes('scripts.desktop_bridge')) args[1] = [${JSON.stringify(path.join(repository, 'tests/fixtures/settings_bridge.py'))}];
  const child = originalSpawn(...args); log({ kind: 'bridge', pid: child.pid }); return child; };
app.on('browser-window-created', () => log({ kind: 'window' }));
app.on('second-instance', () => { globalThis.secondLaunches = (globalThis.secondLaunches || 0) + 1; });
const ready = app.whenReady.bind(app);
app.whenReady = () => {
  app.whenReady = ready;
  return ready().then(() => new Promise((resolve) => { globalThis.releaseStartup = resolve; }));
};
app.setAppPath(${JSON.stringify(path.resolve('.'))});
require(${JSON.stringify(path.resolve('out/main/main.cjs'))});
`)
delete process.env.ELECTRON_RUN_AS_NODE
const env = {
  ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(CENSOR_|PYTHON|ELECTRON_RENDERER_URL)/i.test(key))),
  CENSOR_PYTHON: python, CENSOR_APP_DATA_DIR: path.join(root, 'app-data'),
  CENSOR_RUNTIME_ASSETS_DIR: path.join(root, 'runtime'), HF_HUB_OFFLINE: '1',
}
const cases = []
const app = await electron.launch({ args: [harness], env })
async function secondLaunch() {
  const child = spawn(executable, [harness], { env, windowsHide: true, stdio: 'ignore' })
  const timeout = setTimeout(() => child.kill(), 15_000)
  try {
    const code = await new Promise((resolve, reject) => {
      child.once('exit', resolve)
      child.once('error', reject)
    })
    assert.equal(code, 0, 'Second launch must exit cleanly without a bridge or window')
  } finally { clearTimeout(timeout) }
}
async function ownership() {
  const entries = (await readFile(events, 'utf8')).trim().split('\n').map((line) => JSON.parse(line))
  assert.equal(entries.filter((event) => event.kind === 'bridge').length, 1)
  assert.equal(entries.filter((event) => event.kind === 'window').length, 1)
  const ownerPid = await app.evaluate(() => process.pid)
  assert.ok(entries.every((event) => event.owner === ownerPid))
  assert.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length), 1)
}
try {
  assert.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length), 0)
  await secondLaunch()
  assert.equal(await app.evaluate(() => globalThis.secondLaunches), 1)
  await app.evaluate(() => globalThis.releaseStartup())
  const page = await app.firstWindow()
  await page.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()
  await ownership()
  assert.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isFocused()), true)
  cases.push('second-launch-during-startup')

  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].minimize())
  await secondLaunch()
  assert.equal(await app.evaluate(() => globalThis.secondLaunches), 2)
  assert.deepEqual(await app.evaluate(({ BrowserWindow }) => {
    const window = BrowserWindow.getAllWindows()[0]
    return { minimized: window.isMinimized(), visible: window.isVisible(), focused: window.isFocused() }
  }), { minimized: false, visible: true, focused: true })
  await ownership()
  cases.push('second-launch-restores-and-focuses')

  // CLI and desktop run as independent Python processes against the same stores.
  await Promise.all([
    promisify(execFile)(python, ['backend_app.py', 'dictionary', 'add', 'exclude', 'synthetic-cli-entry'], { cwd: repository, env, windowsHide: true }),
    page.evaluate(() => window.expletiveDeleted.invoke('dictionary.add', { target: 'exclude', word: 'synthetic-desktop-entry' })),
  ])
  const payload = JSON.parse(await readFile(path.join(root, 'app-data/dictionary/exclusions.json'), 'utf8'))
  const words = new Set(payload.entries.map((entry) => entry.value))
  assert.ok(words.has('synthetic-cli-entry'))
  assert.ok(words.has('synthetic-desktop-entry'))
  await ownership()
  cases.push('cli-and-desktop-edits-survive')
  const snapshot = () => page.evaluate(() => window.expletiveDeleted.invoke('settings.get'))
  const patchSettings = (changes) => page.evaluate(async (values) => {
    const base = await window.expletiveDeleted.invoke('settings.get')
    return window.expletiveDeleted.invoke('settings.patch', {
      revision: base.revision,
      changes: Object.entries(values).map(([field, value]) => {
        const [group, key] = field.split('.')
        return { field, value, expected: base.settings[group][key] }
      }),
    })
  }, changes)
  async function waitForMarker(name) {
    const deadline = Date.now() + 30_000
    while (!existsSync(path.join(root, `${name}.started`))) {
      if (Date.now() > deadline) throw new Error(`Timed out waiting for ${name}`)
      await new Promise((resolve) => setTimeout(resolve, 30))
    }
  }
  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('heading', { name: 'Prepare this computer', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Review setup', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Continue', exact: true }).click()
  await waitForMarker('install')
  const manualCache = path.join(root, 'manual-cache')
  assert.equal((await patchSettings({ 'runtime.whisper_cache': manualCache, 'censoring.padding_before_ms': 325, 'source.scan_subdirectories': false })).status, 'saved')
  await writeFile(path.join(root, 'install.release'), 'go')
  const dialog = page.getByRole('dialog', { name: 'Review component settings' })
  await dialog.waitFor()
  assert.equal((await snapshot()).settings.runtime.whisper_cache, manualCache)
  await mkdir('test-results', { recursive: true })
  for (const [width, height] of [[1060, 720], [1440, 940]]) {
    await app.evaluate(({ BrowserWindow }, [w, h]) => BrowserWindow.getAllWindows()[0].setSize(w, h), [width, height])
    for (const theme of ['light', 'dark']) {
      await page.evaluate((value) => { document.documentElement.dataset.theme = value }, theme)
      await page.screenshot({ path: `test-results/settings-conflict-${theme}-${width}.png` })
      assert.ok(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth), 'Conflict content must fit horizontally')
    }
  }
  await dialog.getByRole('radio', { name: /Use verified/ }).check()
  await patchSettings({ 'processing.device': 'cpu' })
  await dialog.getByRole('button', { name: 'Apply choices' }).click()
  // A new revision requires another explicit choice; no automatic forced retry.
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('[role="dialog"] button')].find((item) => item.textContent === 'Apply choices')
    return button?.disabled === true
  })
  await dialog.getByRole('radio', { name: /Keep current/ }).check()
  await dialog.getByRole('button', { name: 'Apply choices' }).click()
  await dialog.waitFor({ state: 'hidden' })
  assert.equal(await readFile(path.join(root, 'install-count.txt'), 'utf8'), '1')
  assert.equal(await readFile(path.join(root, 'runtime/models/whisper/completed-download.fixture'), 'utf8'), 'completed synthetic download')
  assert.equal((await snapshot()).settings.runtime.whisper_cache, manualCache)
  cases.push('setup-conflict-repeated-resolution-without-reinstall')

  // The actual inspection request captures its baseline before a concurrent save.
  const verifiedYtdlp = path.join(root, 'verified', 'yt-dlp.exe')
  await page.evaluate((selected) => {
    window.locateResult = window.expletiveDeleted.invoke('dependencies.locate_ytdlp', { path: selected })
  }, verifiedYtdlp)
  await waitForMarker('inspection')
  await patchSettings({ 'runtime.ytdlp_path': path.join(root, 'manual', 'yt-dlp.exe'), 'censoring.padding_after_ms': 425 })
  await writeFile(path.join(root, 'inspection.release'), 'go')
  const inspected = await page.evaluate(() => window.locateResult)
  assert.equal(inspected.status, 'awaiting_resolution')
  const resolved = await page.evaluate((state) => window.expletiveDeleted.invoke('dependencies.resolve_conflict', {
    install_id: state.install_id, revision: state.resolution.snapshot.revision,
    choices: { 'runtime.ytdlp_path': 'use_verified' },
  }), inspected)
  assert.equal(resolved.status, 'completed')
  assert.equal((await snapshot()).settings.runtime.ytdlp_path, verifiedYtdlp)
  cases.push('inspection-preserves-newer-preferences')

  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('heading', { name: 'Choose your settings', exact: true }).waitFor()
  await page.getByRole('button', { name: /^Keep my current dictionary/ }).click()
  await page.getByRole('button', { name: 'Karaoke', exact: true }).click()
  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('heading', { name: 'Add a first file', exact: true }).waitFor()
  let current = (await snapshot()).settings
  assert.equal(current.runtime.ytdlp_path, verifiedYtdlp)
  assert.equal(current.runtime.whisper_cache, manualCache)
  assert.equal(current.censoring.padding_before_ms, 325)
  assert.equal(current.censoring.padding_after_ms, 425)
  assert.equal(current.censoring.stereo_method, 'karaoke')
  assert.equal(current.processing.device, 'cpu')
  assert.equal(current.source.scan_subdirectories, false)
  assert.equal(current.onboarding.last_step, 'add-media')
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('button', { name: 'Finish setup', exact: true }).click()
  await page.getByRole('heading', { name: 'Queue', exact: true }).waitFor()
  current = (await snapshot()).settings
  assert.equal(current.onboarding.completed, true)
  assert.equal(current.runtime.ytdlp_path, verifiedYtdlp)
  cases.push('wizard-back-and-finish-preserve-component-settings')

  const cli = await promisify(execFile)(python, ['manage_settings.py', 'set-options', '--device', 'cuda'], { cwd: repository, env, windowsHide: true }).then(() => null, (error) => error)
  assert.equal(cli?.code, 1)
  assert.match(cli.stdout, /Close the desktop/)
  assert.equal((await snapshot()).settings.processing.device, 'cpu')
  cases.push('cli-settings-blocked-by-desktop-owner')
  console.log(`Native state smoke passed: ${cases.join(', ')}`)
} finally {
  await mkdir('test-results', { recursive: true })
  // Keep dictionary and journal contents out of CI artifacts.
  await writeFile('test-results/state.json', JSON.stringify({ cases, complete: cases.length === 7 }, null, 2))
  await app.close()
}
