import { rm } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import path from 'node:path'

const target = process.argv[2]
if (!['dir', 'nsis'].includes(target)) {
  throw new Error('Usage: node scripts/package-windows.mjs <dir|nsis>')
}

const generatedDirectories = [
  path.resolve('release', 'win-unpacked'),
  path.resolve('release', 'win-unpacked.tmp'),
]
const electronBuilder = path.resolve('node_modules', 'electron-builder', 'out', 'cli', 'cli.js')
const maximumAttempts = 3

async function cleanGeneratedDirectories() {
  for (const directory of generatedDirectories) {
    try {
      await rm(directory, { recursive: true, force: true, maxRetries: 8, retryDelay: 250 })
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      throw new Error(
        `Could not clean generated package output ${directory}. Close any packaged `
        + `Expletive Deleted window and any Explorer window open to release, then retry. ${detail}`,
      )
    }
  }
}

function runBuilder() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [
      electronBuilder,
      '--win',
      target === 'dir' ? '--dir' : 'nsis',
      '--publish',
      'never',
    ], {
      cwd: process.cwd(),
      env: Object.fromEntries(
        Object.entries(process.env).filter(([key]) => key !== 'GH_TOKEN' && key !== 'GITHUB_TOKEN'),
      ),
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
    let output = ''
    child.stdout.on('data', (chunk) => {
      const text = chunk.toString()
      output += text
      process.stdout.write(text)
    })
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString()
      output += text
      process.stderr.write(text)
    })
    child.on('error', reject)
    child.on('close', (code) => resolve({ code: code ?? 1, output }))
  })
}

for (let attempt = 1; attempt <= maximumAttempts; attempt += 1) {
  await cleanGeneratedDirectories()
  console.log(`Windows package attempt ${attempt} of ${maximumAttempts}`)
  const result = await runBuilder()
  if (result.code === 0) process.exit(0)

  const transientRenameFailure = /EPERM:[\s\S]*rename[\s\S]*win-unpacked\.tmp[\s\S]*win-unpacked/i.test(result.output)
  if (!transientRenameFailure || attempt === maximumAttempts) process.exit(result.code)
  console.warn('Windows temporarily locked Electron staging output; cleaning it and retrying.')
}