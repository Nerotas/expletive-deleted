import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(scriptsDirectory, '..')
const electronInstaller = path.join(frontendRoot, 'node_modules', 'electron', 'install.js')

if (!existsSync(electronInstaller)) {
  throw new Error('Electron package is missing; npm must install dependencies before its postinstall hook runs.')
}

const normalInstall = spawnSync(process.execPath, [electronInstaller], {
  cwd: frontendRoot,
  stdio: 'inherit',
})

if (normalInstall.status === 0) process.exit(0)

if (process.platform !== 'win32') {
  process.exit(normalInstall.status ?? 1)
}

console.warn('Electron native extraction was blocked; using the verified Windows archive fallback.')
const fallback = spawnSync(
  'powershell.exe',
  [
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    path.join(scriptsDirectory, 'install-electron-runtime.ps1'),
  ],
  { cwd: frontendRoot, stdio: 'inherit' },
)
process.exit(fallback.status ?? 1)
