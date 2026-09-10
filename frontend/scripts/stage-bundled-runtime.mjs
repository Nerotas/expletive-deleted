import { cp, readdir, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const stagingDirectory = path.resolve('runtime', 'windows-x64')
const suppliedDirectory = process.env.BUNDLED_RUNTIME_DIR?.trim()
const suppliedPythonDirectory = process.env.BUNDLED_PYTHON_DIR?.trim()
const runtimeRequired = process.argv.includes('--required') || process.env.REQUIRE_BUNDLED_RUNTIME === '1'
const retainedFiles = new Set(['README.md', 'runtime-manifest.schema.json', 'build-inputs.json'])

if (!suppliedDirectory && runtimeRequired) {
  if (!suppliedPythonDirectory) throw new Error('A packaged release requires BUNDLED_PYTHON_DIR with a private Python runtime payload.')
}

const sourceDirectory = suppliedDirectory ? path.resolve(suppliedDirectory) : undefined
if (sourceDirectory) {
  const audit = spawnSync(process.execPath, ['scripts/audit-bundled-runtime.mjs', sourceDirectory], {
    stdio: 'inherit',
    env: process.env,
  })
  if (audit.status !== 0) process.exit(audit.status ?? 1)
  const verification = spawnSync(process.execPath, ['scripts/verify-bundled-runtime.mjs', sourceDirectory], {
    stdio: 'inherit',
    env: process.env,
  })
  if (verification.status !== 0) process.exit(verification.status ?? 1)
}

for (const entry of await readdir(stagingDirectory, { withFileTypes: true })) {
  if (!retainedFiles.has(entry.name)) await rm(path.join(stagingDirectory, entry.name), { recursive: true, force: true })
}

if (suppliedPythonDirectory) {
  const pythonDirectory = path.resolve(suppliedPythonDirectory)
  const executableName = process.platform === 'win32' ? 'python.exe' : 'python'
  if (!existsSync(path.join(pythonDirectory, executableName))) {
    throw new Error(`BUNDLED_PYTHON_DIR is missing ${executableName}: ${pythonDirectory}`)
  }
  await cp(pythonDirectory, path.join(stagingDirectory, 'python'), { recursive: true, force: true })
}

if (!sourceDirectory) {
  if (suppliedPythonDirectory) console.log(`Staged private Python runtime from ${suppliedPythonDirectory}`)
  else console.log('No BUNDLED_PYTHON_DIR supplied; packaging without the private Python runtime payload.')
  process.exit(0)
}

for (const entry of await readdir(sourceDirectory, { withFileTypes: true })) {
  await cp(path.join(sourceDirectory, entry.name), path.join(stagingDirectory, entry.name), { recursive: true, force: true })
}
console.log(`Staged audited bundled runtime from ${sourceDirectory}`)
