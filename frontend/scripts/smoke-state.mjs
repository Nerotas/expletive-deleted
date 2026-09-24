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
cp.spawn = (...args) => { const child = originalSpawn(...args); log({ kind: 'bridge', pid: child.pid }); return child; };
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
  console.log(`Native state smoke passed: ${cases.join(', ')}`)
} finally {
  await mkdir('test-results', { recursive: true })
  // Keep dictionary and journal contents out of CI artifacts.
  await writeFile('test-results/state.json', JSON.stringify({ cases, complete: cases.length === 3 }, null, 2))
  await app.close()
}
