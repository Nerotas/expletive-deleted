import assert from 'node:assert/strict'
import { copyFile, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { _electron as electron } from 'playwright'

const repository = path.resolve('..')
const localPython = path.join(repository, '.venv', 'Scripts', 'python.exe')
const python = process.env.CENSOR_PYTHON || (existsSync(localPython) ? localPython
  : execFileSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).trim())
await mkdir('node_modules/.tmp', { recursive: true })
const root = await mkdtemp(path.resolve('node_modules/.tmp/native-files-'))
await mkdir(path.join(root, 'scripts'))
await copyFile(path.join(repository, 'tests/fixtures/native_files_bridge.py'), path.join(root, 'scripts/desktop_bridge.py'))
const harness = path.join(root, 'harness.cjs')
await writeFile(harness, `require('electron').app.setAppPath(${JSON.stringify(root)}); require(${JSON.stringify(path.resolve('out/main/main.cjs'))});`)
delete process.env.ELECTRON_RUN_AS_NODE
const app = await electron.launch({ args: [harness], env: {
  ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(CENSOR_|PYTHON|ELECTRON_RENDERER_URL)/i.test(key))),
  CENSOR_PYTHON: python, CENSOR_APP_DATA_DIR: path.join(root, 'app-data'),
  NATIVE_FILES_TEST_REPO: repository, NATIVE_FILES_TEST_ROOT: root,
} })
const cases = []
try {
  const page = await app.firstWindow()
  await page.getByRole('heading', { name: 'Welcome to Expletive Deleted', exact: true }).waitFor()
  const source = path.join(root, 'Ready/film.mp4')
  const output = path.join(root, 'Finished/film-censored.mkv')
  const exported = path.join(root, 'dictionary.json')
  await writeFile(source, 'original')
  await writeFile(output, 'synthetic verified output')
  await app.evaluate(({ shell, dialog }) => {
    globalThis.__nativeFiles = { launches: [], selected: undefined, confirmation: 0 }
    shell.openPath = async (file) => { globalThis.__nativeFiles.launches.push(file); return '' }
    dialog.showSaveDialog = async () => ({ canceled: !globalThis.__nativeFiles.selected, filePath: globalThis.__nativeFiles.selected })
    dialog.showOpenDialog = async () => ({ canceled: !globalThis.__nativeFiles.selected, filePaths: [globalThis.__nativeFiles.selected] })
    dialog.showMessageBox = async () => {
      if (globalThis.__nativeFiles.replaceDuringConfirmation) {
        const fs = await import('node:fs/promises')
        await fs.writeFile(globalThis.__nativeFiles.selected, 'competing result')
      }
      return { response: globalThis.__nativeFiles.confirmation }
    }
  })
  await page.evaluate((source) => window.expletiveDeleted.openOutput(source), source)
  assert.deepEqual(await app.evaluate(() => globalThis.__nativeFiles.launches), [output])
  cases.push('verified-output-handoff')
  for (const candidate of ['bad.exe', 'bad.cmd', 'bad.bat', 'bad.lnk', 'bad.url', 'film.mp4:stream']) {
    await assert.rejects(page.evaluate((source) => window.expletiveDeleted.openOutput(source), path.join(root, 'Ready', candidate)))
  }
  await assert.rejects(page.evaluate((source) => window.expletiveDeleted.openOutput(source), path.join(root, 'external.mp4')))
  assert.deepEqual(await app.evaluate(() => globalThis.__nativeFiles.launches), [output])
  cases.push('unsafe-playback-never-launched')
  for (const method of ['dictionary.export', 'dictionary.import', 'native.dictionary.export', 'native.output.check']) {
    await assert.rejects(page.evaluate(({ method, exported }) => window.expletiveDeleted.invoke(method, { destination: exported, source: exported }), { method, exported }), /approved native file selection/)
  }
  cases.push('generic-bypasses-rejected')
  assert.deepEqual(await page.evaluate(() => window.expletiveDeleted.exportDictionary()), { canceled: true })
  await app.evaluate((_, selected) => { globalThis.__nativeFiles.selected = selected }, exported)
  assert.deepEqual(await page.evaluate(() => window.expletiveDeleted.exportDictionary()), { canceled: false, path: exported })
  const approved = await readFile(exported, 'utf8')
  assert.equal(JSON.parse(approved).schema_version, 2)
  cases.push('approved-native-export')
  assert.deepEqual(await page.evaluate(() => window.expletiveDeleted.exportDictionary()), { canceled: true })
  assert.equal(await readFile(exported, 'utf8'), approved)
  await app.evaluate(() => { globalThis.__nativeFiles.confirmation = 1 })
  await page.evaluate(() => window.expletiveDeleted.exportDictionary())
  assert.equal((await page.evaluate(() => window.expletiveDeleted.importDictionary())).canceled, false)
  cases.push('confirmed-replacement-and-native-import')
  await app.evaluate(() => { globalThis.__nativeFiles.replaceDuringConfirmation = true })
  await assert.rejects(page.evaluate(() => window.expletiveDeleted.exportDictionary()), /changed/)
  assert.equal(await readFile(exported, 'utf8'), 'competing result')
  cases.push('changed-target-retained')
  await app.evaluate((_, root) => { globalThis.__nativeFiles.selected = `${root}/unsafe.exe` }, root)
  await assert.rejects(page.evaluate(() => window.expletiveDeleted.exportDictionary()), /\.json/)
  cases.push('invalid-export-extension')
  console.log(`Native file smoke passed: ${cases.join(', ')}`)
} finally {
  await mkdir('test-results', { recursive: true })
  await writeFile('test-results/native-files.json', JSON.stringify({ cases, complete: cases.length === 7 }, null, 2))
  await app.close()
}
