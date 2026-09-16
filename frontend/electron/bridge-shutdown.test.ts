// @vitest-environment node
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { describe, expect, it } from 'vitest'
import { stopBridge } from './bridge-shutdown.js'

describe('bridge shutdown', () => {
  it('waits for cleanup after stdin EOF instead of terminating immediately', async () => {
    const child = spawn(process.execPath, ['-e', `
      process.stdin.resume();
      process.stdin.on('end', () => setTimeout(() => { console.log('cleaned'); process.exit(0) }, 80));
      console.log('ready');
    `], { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
    try {
      await once(child.stdout, 'data')
      let output = ''
      child.stdout.on('data', (chunk) => { output += chunk.toString() })
      await stopBridge(child, 3000)
      expect(child.exitCode).toBe(0)
      expect(output).toContain('cleaned')
    } finally { if (child.exitCode === null) child.kill('SIGKILL') }
  })

  it('terminates an unresponsive bridge after the grace period', async () => {
    const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000); console.log("ready")'],
      { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
    try {
      await once(child.stdout, 'data')
      await stopBridge(child, 50)
      expect(child.signalCode !== null || child.exitCode !== 0).toBe(true)
      await stopBridge(child, 50)
    } finally { if (child.exitCode === null) child.kill('SIGKILL') }
  })
})
