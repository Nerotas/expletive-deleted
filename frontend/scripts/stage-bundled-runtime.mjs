import { cp, readdir, rm } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const stagingDirectory = path.resolve('runtime', 'windows-x64')
const suppliedDirectory = process.env.BUNDLED_RUNTIME_DIR?.trim()
const runtimeRequired = process.argv.includes('--required') || process.env.REQUIRE_BUNDLED_RUNTIME === '1'
const retainedFiles = new Set(['README.md', 'runtime-manifest.schema.json', 'build-inputs.json'])

if (!suppliedDirectory && runtimeRequired) {
  throw new Error('A bundled release requires BUNDLED_RUNTIME_DIR with an audited Windows runtime payload.')
}

const sourceDirectory = suppliedDirectory ? path.resolve(suppliedDirectory) : undefined
if (sourceDirectory) {
  const audit = spawnSync(process.execPath, ['scripts/audit-bundled-runtime.mjs', sourceDirectory], {
    stdio: 'inherit',
    env: process.env,
  })
  if (audit.status !== 0) process.exit(audit.status ?? 1)
}

for (const entry of await readdir(stagingDirectory, { withFileTypes: true })) {
  if (!retainedFiles.has(entry.name)) await rm(path.join(stagingDirectory, entry.name), { recursive: true, force: true })
}

if (!sourceDirectory) {
  console.log('No BUNDLED_RUNTIME_DIR supplied; packaging without the private runtime payload.')
  process.exit(0)
}

for (const entry of await readdir(sourceDirectory, { withFileTypes: true })) {
  await cp(path.join(sourceDirectory, entry.name), path.join(stagingDirectory, entry.name), { recursive: true, force: true })
}
console.log(`Staged audited bundled runtime from ${sourceDirectory}`)
