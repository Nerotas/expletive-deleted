import { setTimeout as delay } from 'node:timers/promises'

// Only recover transient socket exhaustion while arranging the test document.
// Security assertions and deliberately blocked redirect loads must never retry.
export async function loadSecurityDocument(load, ready, {
  pause = delay,
  onRetry = (attempt) => console.warn(`Security fixture navigation ran out of socket buffer space; retrying (${attempt}/2).`),
} = {}) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      // Registering a navigation waiter before loadURL can observe an earlier,
      // deliberately blocked navigation. Check the actual document after loading.
      await load()
      await ready()
      return
    } catch (error) {
      if (attempt === 2 || !/\bERR_NO_BUFFER_SPACE\b/.test(String(error?.message))) throw error
      onRetry(attempt + 1)
      await pause(100 * (attempt + 1))
    }
  }
}
