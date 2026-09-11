import { access, readFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const suppliedDirectory = process.argv[2] ?? process.env.BUNDLED_RUNTIME_DIR
if (!suppliedDirectory) throw new Error('Pass the runtime directory or set BUNDLED_RUNTIME_DIR.')
if (process.platform !== 'win32') {
  throw new Error('Verify the Windows private Python runtime from a Windows release builder.')
}

const runtimeRoot = path.resolve(suppliedDirectory)
const python = path.join(runtimeRoot, 'python', 'python.exe')
const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
await Promise.all([access(python), access(manifestPath)])
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))

function run(label, args) {
  const result = spawnSync(python, args, {
    encoding: 'utf8',
    timeout: 60_000,
    windowsHide: true,
  })
  if (result.error) throw new Error(`${label} could not start: ${result.error.message}`)
  if (result.status !== 0) {
    const detail = `${result.stdout ?? ''}${result.stderr ?? ''}`.trim()
    throw new Error(`${label} failed${detail ? `: ${detail}` : ''}`)
  }
  return `${result.stdout ?? ''}${result.stderr ?? ''}`
}

// A release runtime is intentionally only CPython plus pip; processing dependencies belong to setup.
const verification = [
  'import importlib.metadata as metadata, platform',
  `assert platform.python_version() == ${JSON.stringify(manifest.python?.version)}, platform.python_version()`,
  `assert metadata.version('pip') == ${JSON.stringify(manifest.pip?.version)}, metadata.version('pip')`,
  "installed = sorted({(item.metadata.get('Name') or '').lower().replace('_', '-') for item in metadata.distributions()})",
  "assert installed == ['pip'], f'unexpected bundled Python distributions: {installed}'",
  "print('Private Python and pip bootstrap verified')",
].join('; ')
run('Private Python bootstrap check', ['-I', '-c', verification])
run('Private pip check', ['-I', '-m', 'pip', '--version'])

console.log(`Private Python runtime executable verification passed: ${runtimeRoot}`)
