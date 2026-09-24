import type { App, BrowserWindow } from 'electron'

type Window = Pick<BrowserWindow, 'isDestroyed' | 'isMinimized' | 'restore' | 'show' | 'focus'>

export function claimDesktopInstance(app: Pick<App, 'requestSingleInstanceLock' | 'quit' | 'on'>) {
  let window: Window | undefined
  let focusPending = false
  const ownsInstance = app.requestSingleInstanceLock()
  if (!ownsInstance) app.quit()
  else app.on('second-instance', () => {
    focusPending = true
    focusWindow()
  })

  function focusWindow() {
    if (!focusPending || !window || window.isDestroyed()) return
    if (window.isMinimized()) window.restore()
    window.show()
    window.focus()
    focusPending = false
  }

  return {
    ownsInstance,
    windowReady(readyWindow: Window) {
      window = readyWindow
      // A second launch can arrive before construction or the first paint.
      focusWindow()
    },
  }
}
