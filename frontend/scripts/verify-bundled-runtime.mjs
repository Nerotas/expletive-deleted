import { access } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const suppliedDirectory = process.argv[2] ?? process.env.BUNDLED_RUNTIME_DIR
if (!suppliedDirectory) throw new Error('Pass the runtime directory or set BUNDLED_RUNTIME_DIR.')
if (process.platform !== 'win32') {
  throw new Error('Verify the Windows bundled runtime from a Windows release builder.')
}

const runtimeRoot = path.resolve(suppliedDirectory)
const python = path.join(runtimeRoot, 'python', 'python.exe')
const ffmpeg = path.join(runtimeRoot, 'ffmpeg', 'ffmpeg.exe')
const ffprobe = path.join(runtimeRoot, 'ffmpeg', 'ffprobe.exe')
const deno = path.join(runtimeRoot, 'deno', 'deno.exe')
await Promise.all([access(python), access(ffmpeg), access(ffprobe), access(deno)])

const environment = {
  ...process.env,
  PATH: `${path.dirname(ffmpeg)}${path.delimiter}${process.env.PATH ?? ''}`,
}

function run(label, command, args) {
  const result = spawnSync(command, args, {
    encoding: 'utf8',
    env: environment,
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

const importCheck = [
  'import av',
  'import ctranslate2',
  'import faster_whisper',
  'import numpy',
  'import better_profanity',
  'import huggingface_hub',
  'assert av.library_versions',
  "print('Private Python imports and PyAV libraries verified')",
].join('; ')
run('Private Python dependency check', python, ['-c', importCheck])

for (const [label, executable] of [['FFmpeg', ffmpeg], ['FFprobe', ffprobe]]) {
  const version = run(`${label} version check`, executable, ['-hide_banner', '-version'])
  if (/--enable-gpl\b|--enable-nonfree\b/.test(version)) {
    throw new Error(`${label} is not an approved LGPL-only build.`)
  }
}

const encoders = run('FFmpeg encoder check', ffmpeg, ['-hide_banner', '-encoders'])
if (/\blibx26[45]\b/i.test(encoders)) {
  throw new Error('Bundled FFmpeg exposes libx264 or libx265, which is not approved for distribution.')
}

run('Deno version check', deno, ['--version'])

console.log(`Bundled Windows runtime executable verification passed: ${runtimeRoot}`)
