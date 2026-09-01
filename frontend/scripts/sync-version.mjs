import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')
const packageJson = JSON.parse(await readFile(path.join(frontendRoot, 'package.json'), 'utf8'))
const version = packageJson.version
const checkOnly = process.argv.includes('--check')

if (!/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error(`Application version must use major.minor.patch format; received ${version}`)
}

const updates = [
  {
    file: path.join(frontendRoot, 'package-lock.json'),
    check(contents) {
      const lock = JSON.parse(contents)
      if (lock.version !== version || lock.packages?.['']?.version !== version) {
        throw new Error(`frontend/package-lock.json does not match version ${version}`)
      }
    },
    transform(contents) {
      const lock = JSON.parse(contents)
      lock.version = version
      lock.packages[''].version = version
      return `${JSON.stringify(lock, null, 2)}\n`
    },
  },
  {
    file: path.join(frontendRoot, 'src', 'features', 'settings', 'SettingsPage.tsx'),
    patterns: [
      [/(\{APPLICATION_DISPLAY_NAME\}\s+)\d+\.\d+\.\d+/, `$1${version}`],
    ],
  },
  {
    file: path.join(repositoryRoot, 'README.md'),
    patterns: [
      [/Version \*\*\d+\.\d+\.\d+\*\*/, `Version **${version}**`],
      [/Expletive-Deleted-Setup-\d+\.\d+\.\d+-x64\.exe/, `Expletive-Deleted-Setup-${version}-x64.exe`],
    ],
  },
  {
    file: path.join(repositoryRoot, 'docs', 'index.html'),
    patterns: [
      [/Version \d+\.\d+\.\d+/, `Version ${version}`],
      [/Expletive Deleted \d+\.\d+\.\d+/, `Expletive Deleted ${version}`],
    ],
  },
]

for (const update of updates) {
  const original = await readFile(update.file, 'utf8')
  if (checkOnly && update.check) {
    update.check(original)
    continue
  }
  let contents = update.transform ? update.transform(original) : original
  for (const [pattern, replacement] of update.patterns ?? []) {
    if (!pattern.test(contents)) {
      throw new Error(`Could not find ${pattern} in ${path.relative(repositoryRoot, update.file)}`)
    }
    contents = contents.replace(pattern, replacement)
  }
  if (checkOnly && contents !== original) {
    throw new Error(`${path.relative(repositoryRoot, update.file)} does not match version ${version}`)
  }
  if (!checkOnly) await writeFile(update.file, contents, 'utf8')
}

console.log(`${checkOnly ? 'Verified' : 'Synchronized'} application version ${version}`)
