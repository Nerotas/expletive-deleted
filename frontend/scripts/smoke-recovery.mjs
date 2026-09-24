import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { _electron as electron } from 'playwright'

const repository = path.resolve('..')
const localPython = path.join(repository, '.venv/Scripts/python.exe')
const python = process.env.CENSOR_PYTHON || (existsSync(localPython) ? localPython
  : execFileSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).trim())
await mkdir('node_modules/.tmp', { recursive: true })
await mkdir('test-results', { recursive: true })
const root = await mkdtemp(path.resolve('node_modules/.tmp/recovery-'))
const harness = path.join(root, 'harness.cjs')
// Fault injection is confined to the native test harness and offline fixture.
// The renderer, preload, transport and Python dispatch are production code.
await writeFile(harness, `
const { app } = require('electron');
const fs = require('node:fs');
const cp = require('node:child_process');
const spawn = cp.spawn;
cp.spawn = (...args) => {
  if (args[1]?.includes('scripts.desktop_bridge')) {
    args[1] = [${JSON.stringify(path.join(repository, 'tests/fixtures/recovery_bridge.py'))}];
    globalThis.smokeBridge = spawn(...args); return globalThis.smokeBridge;
  }
  return spawn(...args);
};
// Relaunch is recorded so Playwright can attach to the next explicit launch.
app.relaunch = () => fs.writeFileSync(${JSON.stringify(path.join(root, 'restart.requested'))}, 'requested');
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
const required = ['lost-start-ack', 'transient-recovery', 'saturated-control-and-lost-cancel-ack', 'real-30-second-silence',
  'status-only-retry', 'known-backend-exit', 'explicit-restart-retains-files-and-requires-approval']
let app = await electron.launch({ args: [harness], env })
let page
const marker = (name, value = 'go') => writeFile(path.join(root, name), value)
const remove = (name) => rm(path.join(root, name), { force: true })
async function waitUntil(check, message) {
  const deadline = performance.now() + 20_000
  while (!(await check())) {
    if (performance.now() >= deadline) throw new Error(message)
    await new Promise((resolve) => setTimeout(resolve, 40))
  }
}
const count = async () => Number(await readFile(path.join(root, 'install-count.txt'), 'utf8'))
const asset = path.join(root, 'runtime/models/whisper/completed-download.fixture')
async function approve() {
  await page.getByRole('button', { name: 'Review setup', exact: true }).click()
  const consent = page.getByRole('dialog')
  await consent.getByRole('button', { name: 'Continue', exact: true }).click()
}
async function visuals(phase) {
  const dialog = page.getByRole('dialog')
  for (const [width, height] of [[1060, 720], [1440, 940]]) {
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setSize(...size), [width, height])
    for (const theme of ['light', 'dark']) {
      await page.evaluate((value) => { document.documentElement.dataset.theme = value }, theme)
      await page.screenshot({ path: `test-results/recovery-${phase}-${theme}-${width}.png` })
      assert.ok(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth), 'Recovery must fit horizontally')
      assert.ok(await dialog.evaluate((element) => element.getBoundingClientRect().bottom <= window.innerHeight), 'Actions must fit vertically')
      assert.equal(await page.locator('.runtime-pill.installing').isVisible(), true, 'Background setup must remain reachable at every supported size')
    }
  }
  await dialog.focus()
  await page.keyboard.press('Tab')
  assert.equal(await page.getByRole('button', { name: 'Dismiss installation progress' }).evaluate((element) => element === document.activeElement), true)
  await page.keyboard.press('Shift+Tab')
  assert.equal(await dialog.evaluate((element) => element.contains(document.activeElement)), true)
  assert.equal(await dialog.getByRole('status').getAttribute('aria-live'), 'polite')
  await dialog.getByRole('button', { name: 'Background', exact: true }).click()
  await page.locator('.runtime-pill.installing').focus()
  await page.keyboard.press('Enter')
  await dialog.waitFor()
}
try {
  page = await app.firstWindow()
  await page.getByRole('button', { name: 'Save & Continue' }).click()
  await page.getByRole('heading', { name: 'Prepare this computer', exact: true }).waitFor()
  await marker('mode', 'start')
  await approve()
  await page.getByRole('heading', { name: 'Preparing required components', exact: true }).waitFor()
  assert.equal(await count(), 1)
  cases.push('lost-start-ack')

  await marker('mode', 'silence')
  await page.getByRole('heading', { name: 'Reconnecting to setup' }).waitFor()
  await visuals('reconnecting')
  await marker('mode', '')
  await page.getByRole('heading', { name: 'Preparing required components', exact: true }).waitFor()
  assert.equal(await count(), 1)
  cases.push('transient-recovery')

  await marker('saturate')
  await page.evaluate(() => {
    window.saturation = Promise.all(Array.from({ length: 4 }, () => window.expletiveDeleted.invoke('capabilities.get')))
  })
  await waitUntil(async () => existsSync(path.join(root, 'saturated.jsonl')) && (await readFile(path.join(root, 'saturated.jsonl'), 'utf8')).trim().split('\n').length === 4, 'Four normal workers must be occupied')
  const control = await page.evaluate(async () => {
    const start = performance.now()
    // Find the only active approval from the fixture's UI start by querying no
    // private state: the last actual status remains available through the UI.
    const plan = await window.expletiveDeleted.invoke('dependencies.active', { plan_id: 'unknown' })
    return { elapsed: performance.now() - start, plan }
  })
  assert.equal(control.plan, null)
  assert.ok(control.elapsed < 1900)
  await marker('mode', 'silence')
  await page.getByRole('button', { name: 'Cancel setup', exact: true }).click()
  await waitUntil(() => existsSync(path.join(root, 'cancel.received')), 'Cancellation must reach the worker under saturation')
  await page.getByRole('heading', { name: 'Reconnecting to setup' }).waitFor()
  assert.equal(await page.getByText('Installation complete and verified', { exact: true }).count(), 0)
  await remove('saturate')
  await page.evaluate(() => window.saturation)
  await marker('mode', '')
  await page.getByRole('heading', { name: 'Cancelling installation', exact: true }).waitFor()
  await marker('install.release')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.equal(await count(), 1)
  assert.equal(await readFile(asset, 'utf8'), 'completed synthetic download')
  cases.push('saturated-control-and-lost-cancel-ack')

  await remove('install.release')
  await remove('cancel.received')
  await approve()
  await page.getByRole('heading', { name: 'Preparing required components', exact: true }).waitFor()
  await marker('mode', 'silence')
  await page.getByRole('heading', { name: 'Reconnecting to setup' }).waitFor()
  const lossAt = performance.now()
  // Use the real production window. No fake clock or shortened constants here.
  await page.getByRole('heading', { name: 'Setup needs attention', exact: true }).waitFor({ timeout: 35_000 })
  const silence = performance.now() - lossAt
  assert.ok(silence >= 29_500 && silence <= 32_000, `Reconnection window was ${silence}ms`)
  await page.getByText(/The installation outcome is unknown/).waitFor()
  await visuals('recovery')
  assert.equal(await count(), 2)
  cases.push('real-30-second-silence')
  await marker('mode', '')
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click()
  await page.getByRole('heading', { name: 'Preparing required components', exact: true }).waitFor()
  assert.equal(await count(), 2)
  cases.push('status-only-retry')

  const exitAt = performance.now()
  await app.evaluate(() => globalThis.smokeBridge.kill('SIGKILL'))
  await page.getByText(/The local processing service has stopped/).waitFor({ timeout: 5000 })
  assert.ok(performance.now() - exitAt < 2500)
  assert.equal(await page.getByRole('button', { name: 'Retry connection' }).isDisabled(), true)
  assert.equal(await readFile(asset, 'utf8'), 'completed synthetic download')
  cases.push('known-backend-exit')
  const closed = app.waitForEvent('close')
  await page.getByRole('button', { name: 'Restart app', exact: true }).click()
  await closed
  assert.ok(existsSync(path.join(root, 'restart.requested')))
  app = await electron.launch({ args: [harness], env })
  page = await app.firstWindow()
  await page.getByRole('heading', { name: 'Prepare this computer', exact: true }).waitFor()
  assert.equal(await count(), 2)
  assert.equal(await readFile(asset, 'utf8'), 'completed synthetic download')
  await page.getByRole('button', { name: 'Review setup', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Continue', exact: true }).waitFor()
  assert.equal(await count(), 2, 'A fresh plan must await explicit approval after restart')
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  cases.push('explicit-restart-retains-files-and-requires-approval')
  assert.deepEqual(cases, required)
  console.log(`Native recovery smoke passed (${cases.length} cases, real silence ${Math.round(silence)}ms).`)
} catch (error) {
  await page?.screenshot({ path: 'test-results/recovery-failure.png' }).catch(() => {})
  throw error
} finally {
  await writeFile('test-results/recovery.json', JSON.stringify({ cases, required, complete: cases.length === required.length }, null, 2))
  await marker('install.release')
  await remove('saturate')
  await app.close().catch(() => {})
}
