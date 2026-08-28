import { spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const tempDirectory = path.resolve('node_modules', '.tmp', 'vitest')
mkdirSync(tempDirectory, { recursive: true })

const argumentsFromCommandLine = process.argv.slice(2)
const argumentsForVitest = argumentsFromCommandLine.length ? argumentsFromCommandLine : ['run']
const result = spawnSync(
  process.execPath,
  [path.resolve('node_modules', 'vitest', 'vitest.mjs'), ...argumentsForVitest],
  {
    stdio: 'inherit',
    env: {
      ...process.env,
      TMPDIR: tempDirectory,
      TMP: tempDirectory,
      TEMP: tempDirectory,
    },
  },
)

if (result.error) throw result.error
process.exit(result.status ?? 1)

