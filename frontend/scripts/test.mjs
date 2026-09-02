import { execFileSync, spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const tempDirectory = path.resolve('node_modules', '.tmp', 'vitest')
mkdirSync(tempDirectory, { recursive: true })

// Newer Node defaults its native Web Storage API on, which shadows jsdom's localStorage in
// vitest's worker processes; those workers only inherit NODE_OPTIONS, not parent CLI flags.
function supportsDisablingNativeWebStorage() {
  try {
    return execFileSync(process.execPath, ['--help'], { encoding: 'utf8' }).includes('webstorage')
  } catch {
    return false
  }
}

const nodeOptions = [process.env.NODE_OPTIONS, supportsDisablingNativeWebStorage() ? '--no-experimental-webstorage' : '']
  .filter(Boolean)
  .join(' ')
const argumentsFromCommandLine = process.argv.slice(2)
const argumentsForVitest = argumentsFromCommandLine.length ? argumentsFromCommandLine : ['run']
const result = spawnSync(
  process.execPath,
  [path.resolve('node_modules', 'vitest', 'vitest.mjs'), ...argumentsForVitest],
  {
    stdio: 'inherit',
    env: {
      ...process.env,
      NODE_OPTIONS: nodeOptions,
      TMPDIR: tempDirectory,
      TMP: tempDirectory,
      TEMP: tempDirectory,
    },
  },
)

if (result.error) throw result.error
process.exit(result.status ?? 1)

