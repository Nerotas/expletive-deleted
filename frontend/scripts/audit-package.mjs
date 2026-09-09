import { readdir } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'

const packageRoot = path.resolve('release', 'win-unpacked')
const bundledRuntimeRoot = path.join(packageRoot, 'resources', 'app-runtime')
const bundledRuntimeManifest = path.join(bundledRuntimeRoot, 'runtime-manifest.json')
const requireBundledRuntime = process.env.REQUIRE_BUNDLED_RUNTIME === '1'
const violations = []
let electronCodecDlls = 0

if (existsSync(bundledRuntimeManifest)) {
  const audit = spawnSync(process.execPath, ['scripts/audit-bundled-runtime.mjs', bundledRuntimeRoot], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (audit.status !== 0) violations.push(`Bundled runtime audit failed: ${(audit.stderr || audit.stdout).trim()}`)
} else if (requireBundledRuntime) {
  violations.push('Expected an audited bundled runtime at resources/app-runtime')
}

async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name)
    const relativePath = path.relative(packageRoot, absolutePath).replaceAll('\\', '/')
    const normalizedName = entry.name.toLowerCase()

    if (entry.isDirectory()) {
      if (relativePath === 'resources/app-runtime' && existsSync(bundledRuntimeManifest)) continue
      if (normalizedName === 'whisper-cache' || normalizedName.startsWith('models--')) {
        violations.push(relativePath)
      }
      await inspect(absolutePath)
      continue
    }

    if (normalizedName === 'ffmpeg.dll') {
      if (relativePath !== 'ffmpeg.dll') violations.push(relativePath)
      electronCodecDlls += 1
      continue
    }

    if (
      normalizedName === 'ffmpeg.exe'
      || normalizedName === 'ffprobe.exe'
      || normalizedName === 'model.bin'
      || normalizedName.endsWith('.pt')
      || normalizedName.endsWith('.whl')
      || normalizedName.endsWith('.pyd')
    ) {
      violations.push(relativePath)
    }
  }
}

await inspect(packageRoot)

if (electronCodecDlls !== 1) {
  violations.push(`Expected one framework-owned root ffmpeg.dll; found ${electronCodecDlls}`)
}
if (violations.length) {
  throw new Error(`Packaged dependency policy violation:\n- ${violations.join('\n- ')}`)
}

console.log('Package dependency audit passed: no unapproved runtime, Whisper model, or Python package artifacts were found')