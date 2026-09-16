import type { ChildProcessWithoutNullStreams } from 'node:child_process'

/** EOF asks Python to cancel workers and remove staging files before exiting. */
export function stopBridge(child: ChildProcessWithoutNullStreams, graceMs = 15_000): Promise<void> {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return Promise.resolve()
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      // The Windows bridge owns a kill-on-close Job Object, so this also ends
      // descendants even if a native model or media tool ignores cancellation.
      child.kill('SIGKILL')
    }, graceMs)
    child.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
    // A broken input pipe is handled by the exit event or the bounded fallback.
    child.stdin.on('error', () => undefined)
    child.stdin.end()
  })
}
