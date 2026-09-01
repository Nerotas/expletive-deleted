import { readdir } from 'node:fs/promises'
import path from 'node:path'

const packageRoot = path.resolve('release', 'win-unpacked')
const violations = []
let electronCodecDlls = 0

async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name)
    const relativePath = path.relative(packageRoot, absolutePath).replaceAll('\\', '/')
    const normalizedName = entry.name.toLowerCase()

    if (entry.isDirectory()) {
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

console.log('Package dependency audit passed: no processing FFmpeg/FFprobe, Whisper models, or Python binary packages bundled')