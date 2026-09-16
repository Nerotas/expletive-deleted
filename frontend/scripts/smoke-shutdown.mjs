import { copyFile, mkdir, mkdtemp, readFile, writeFile, access } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { _electron as electron } from 'playwright'

const repository = path.resolve('..')
const localPython = path.join(repository, '.venv', 'Scripts', 'python.exe')
const python = process.env.CENSOR_PYTHON || (existsSync(localPython)
  ? localPython
  : execFileSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).trim())
const temporaryRoot = path.resolve('node_modules', '.tmp', 'shutdown-smoke')
await mkdir(temporaryRoot, { recursive: true })
delete process.env.ELECTRON_RUN_AS_NODE

async function waitForFile(file) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try { await access(file); return } catch { await delay(50) }
  }
  throw new Error(`Shutdown fixture never reached processing: ${file}`)
}

for (const hung of [false, true]) {
  const root = await mkdtemp(path.join(temporaryRoot, hung ? 'forced-' : 'graceful-'))
  await mkdir(path.join(root, 'scripts'))
  await copyFile(path.join(repository, 'tests', 'fixtures', 'shutdown_bridge.py'), path.join(root, 'scripts', 'desktop_bridge.py'))
  const harness = path.join(root, 'harness.cjs')
  // Load the actual built Electron entrypoint; only the processing fixture changes.
  await writeFile(harness, `require('electron').app.setAppPath(${JSON.stringify(root)}); require(${JSON.stringify(path.resolve('out/main/main.cjs'))});`)
  const app = await electron.launch({
    args: [harness],
    env: {
      ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(CENSOR_|PYTHON|ELECTRON_RENDERER_URL)/i.test(key))),
      CENSOR_PYTHON: python,
      CENSOR_APP_DATA_DIR: path.join(root, 'app-data'),
      SHUTDOWN_TEST_REPO: repository,
      SHUTDOWN_TEST_ROOT: root,
      SHUTDOWN_TEST_HANG: hung ? '1' : '0',
    },
  })
  try {
    const window = await app.firstWindow()
    await window.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()
    const source = path.join(root, 'Ready', 'movie.mkv')
    await writeFile(source, 'original synthetic media')
    await writeFile(path.join(root, 'Transcripts', 'movie-transcript.json'), '{}')
    await window.evaluate((source) => window.expletiveDeleted.invoke('jobs.submit', { source, mode: 'censor' }), source)
    await waitForFile(path.join(root, 'started'))
    const exiting = new Promise((resolve) => app.process().once('exit', resolve))
    await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].close() })
    const timeout = setTimeout(() => app.process().kill(), 25_000)
    try { await exiting } finally { clearTimeout(timeout) }
    if (!hung) await access(path.join(root, 'cancelled'))
    if (await readFile(source, 'utf8') !== 'original synthetic media') throw new Error('Shutdown modified the source')
    const finalExists = await access(path.join(root, 'Finished', 'movie-censored.mkv')).then(() => true, () => false)
    if (finalExists) throw new Error('Shutdown published incomplete output')
    const childPid = Number(await readFile(path.join(root, 'child.pid'), 'utf8'))
    let alive = true
    for (let attempt = 0; attempt < 100; attempt += 1) {
      try { process.kill(childPid, 0) } catch { alive = false; break }
      await delay(50)
    }
    if (alive) throw new Error(`Shutdown left an encoder running: ${childPid}`)
    console.log(`Electron ${hung ? 'forced' : 'graceful'} shutdown smoke passed`)
  } finally {
    await app.close().catch(() => undefined)
  }
}
