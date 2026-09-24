import { describe, expect, it, vi } from 'vitest'
import { claimDesktopInstance } from './single-instance.js'

function fixture(ownsInstance = true) {
  const app = { requestSingleInstanceLock: vi.fn(() => ownsInstance), quit: vi.fn(), on: vi.fn() }
  const window = { isDestroyed: () => false, isMinimized: () => true, restore: vi.fn(), show: vi.fn(), focus: vi.fn() }
  const instance = claimDesktopInstance(app as unknown as Parameters<typeof claimDesktopInstance>[0])
  return { app, window, instance, secondLaunch: () => app.on.mock.calls[0][1]() }
}

describe('desktop instance ownership', () => {
  it('exits a losing launch without registering an owner', () => {
    const { app, instance } = fixture(false)
    expect(instance.ownsInstance).toBe(false)
    expect(app.quit).toHaveBeenCalledOnce()
    expect(app.on).not.toHaveBeenCalled()
  })
  it('retains a focus request until the window is ready', () => {
    const { instance, window, secondLaunch } = fixture()
    secondLaunch()
    expect(window.focus).not.toHaveBeenCalled()
    instance.windowReady(window)
    expect(window.restore).toHaveBeenCalledOnce()
    expect(window.show).toHaveBeenCalledOnce()
    expect(window.focus).toHaveBeenCalledOnce()
  })
  it('restores and focuses the ready window on subsequent launches', () => {
    const { instance, window, secondLaunch } = fixture()
    instance.windowReady(window)
    secondLaunch()
    secondLaunch()
    expect(window.focus).toHaveBeenCalledTimes(2)
  })
})
