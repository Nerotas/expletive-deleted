import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { _electron as electron } from 'playwright'

const repository = path.resolve('..')
await mkdir('node_modules/.tmp', { recursive: true })
const root = await mkdtemp(path.resolve('node_modules/.tmp/system-check-'))
const artifacts = path.join(repository, 'output/playwright/system-check')
await mkdir(artifacts, { recursive: true })
const harness = path.join(root, 'harness.cjs')
// Only the test launch substitutes an offline dependency check. The renderer,
// transport, preload, and Python request dispatcher are production code.
await writeFile(harness, `
const { app } = require('electron');
const cp = require('node:child_process');
const spawn = cp.spawn;
cp.spawn = (...args) => {
  if (args[1]?.includes('scripts.desktop_bridge')) {
    args[1] = [${JSON.stringify(path.join(repository, 'tests/fixtures/system_check_bridge.py'))}];
  }
  return spawn(...args);
};
app.setAppPath(${JSON.stringify(path.resolve('.'))});
require(${JSON.stringify(path.resolve('out/main/main.cjs'))});
`)
const env = {
  ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(CENSOR_|PYTHON|ELECTRON_RENDERER_URL|ELECTRON_RUN_AS_NODE)/i.test(key))),
  CENSOR_PYTHON: path.join(repository, '.venv/Scripts/python.exe'),
  CENSOR_APP_DATA_DIR: path.join(root, 'app-data'),
  CENSOR_RUNTIME_ASSETS_DIR: path.join(root, 'runtime'), HF_HUB_OFFLINE: '1',
}
const app = await electron.launch({ args: [harness], env })
let released = false
try {
  const page = await app.firstWindow()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.getByRole('heading', { name: 'Queue', exact: true }).waitFor()
  await page.getByRole('link', { name: 'Settings', exact: true }).click()
  const karaoke = page.getByRole('button', { name: 'Karaoke', exact: true })
  await karaoke.click()
  assert.equal(await karaoke.getAttribute('aria-pressed'), 'true')
  assert.equal(await page.getByRole('button', { name: 'Save changes', exact: true }).isEnabled(), true)
  const status = page.getByRole('region', { name: 'System check', exact: true })
  await status.getByText(/s elapsed/).waitFor()
  async function visuals(phase) {
    for (const [width, height] of [[1060, 720], [1440, 900]]) {
      await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setSize(...size), [width, height])
      for (const theme of ['light', 'dark']) {
        await page.evaluate((value) => { document.documentElement.dataset.theme = value }, theme)
        await page.screenshot({ path: path.join(artifacts, `${phase}-${theme}-${width}.png`) })
        assert.equal(await status.evaluate((element) => element.scrollWidth <= element.clientWidth), true)
      }
    }
  }
  await visuals('checking')
  // Exercise the real 60-second deadline, rather than a shortened test constant.
  const retry = page.getByRole('button', { name: 'Retry system check', exact: true })
  await retry.waitFor({ timeout: 70_000 })
  await page.getByText('System check failed', { exact: true }).waitFor()
  assert.match(await status.getByRole('alert').innerText(), /60 seconds/)
  assert.equal(Number(await readFile(path.join(root, 'check-count.txt'), 'utf8')), 1)
  assert.equal(await karaoke.getAttribute('aria-pressed'), 'true')
  assert.equal(await page.getByRole('button', { name: 'Save changes', exact: true }).isEnabled(), true)
  await visuals('recovery')
  await retry.focus()
  assert.equal(await retry.evaluate((element) => element === document.activeElement), true)
  await page.keyboard.press('Enter')
  await page.getByText('Processing ready', { exact: true }).waitFor()
  assert.equal(Number(await readFile(path.join(root, 'check-count.txt'), 'utf8')), 2)
  await writeFile(path.join(root, 'release-first-check'), 'release')
  released = true
  // The old response reports missing readiness; it must not replace the retry.
  await page.waitForTimeout(1000)
  await readFile(path.join(root, 'first-check-finished'))
  assert.equal(await page.getByText('Processing ready', { exact: true }).isVisible(), true)
  assert.equal(await karaoke.getAttribute('aria-pressed'), 'true')
  const persisted = await page.evaluate(() => window.expletiveDeleted.invoke('settings.get'))
  assert.equal(persisted.settings.censoring.stereo_method, 'drop_audio')
  assert.deepEqual(errors, [])
  console.log('System-check smoke passed: real deadline, keyboard retry, late-response isolation, retained draft, light/dark at 1060/1440px')
} finally {
  if (!released) await writeFile(path.join(root, 'release-first-check'), 'cleanup')
  await app.close()
}
