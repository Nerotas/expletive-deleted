import { cp, readdir, rm } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const stagingDirectory = path.resolve('runtime', 'windows-x64')
const suppliedDirectory = process.env.BUNDLED_RUNTIME_DIR?.trim()
const retainedFiles = new Set(['README.md', 'runtime-manifest.schema.json', 'build-inputs.json'])

for (const entry of await readdir(stagingDirectory, { withFileTypes: true })) {
  if (!retainedFiles.has(entry.name)) await rm(path.join(stagingDirectory, entry.name), { recursive: true, force: true })
}

if (!suppliedDirectory) {
  if (process.env.REQUIRE_BUNDLED_RUNTIME === '1') {
    throw new Error('REQUIRE_BUNDLED_RUNTIME=1 requires BUNDLED_RUNTIME_DIR.')
  }
  console.log('No BUNDLED_RUNTIME_DIR supplied; packaging without the private runtime payload.')
  process.exit(0)
}

const sourceDirectory = path.resolve(suppliedDirectory)
const audit = spawnSync(process.execPath, ['scripts/audit-bundled-runtime.mjs', sourceDirectory], {
  stdio: 'inherit',
  env: process.env,
})
if (audit.status !== 0) process.exit(audit.status ?? 1)

for (const entry of await readdir(sourceDirectory, { withFileTypes: true })) {
  await cp(path.join(sourceDirectory, entry.name), path.join(stagingDirectory, entry.name), { recursive: true, force: true })
}
console.log(`Staged audited bundled runtime from ${sourceDirectory}`)
