import type { BrowserWindow, IpcMain, IpcMainInvokeEvent } from 'electron'
import type { RendererPolicy } from './renderer-policy.js'

export function secureRendererWindow(window: BrowserWindow, policy: RendererPolicy) {
  let documentGeneration = 0
  const contents = window.webContents
  contents.on('did-start-navigation', (event) => {
    if (event.isMainFrame && !event.isSameDocument) documentGeneration += 1
  })
  contents.on('will-navigate', (event) => {
    if (!policy.allows(event.url)) event.preventDefault()
  })
  contents.on('will-frame-navigate', (event) => {
    if (!event.isMainFrame || !policy.allows(event.url)) event.preventDefault()
  })
  contents.on('will-redirect', (event) => {
    if (!event.isMainFrame || !policy.allows(event.url)) event.preventDefault()
  })
  contents.setWindowOpenHandler(() => ({ action: 'deny' }))
  contents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
  contents.session.setPermissionCheckHandler(() => false)
  return { window, policy, generation: () => documentGeneration }
}

export type TrustedRenderer = ReturnType<typeof secureRendererWindow>
export type TrustedRequest = { window: BrowserWindow; assertCurrent: () => void }

export function authorizeRenderer(event: IpcMainInvokeEvent, getRenderer: () => TrustedRenderer | undefined): TrustedRequest {
  const renderer = getRenderer()
  const generation = renderer?.generation()
  const frame = event.senderFrame
  const assertCurrent = () => {
    let trusted = false
    try {
      trusted = Boolean(renderer && getRenderer() === renderer
        && renderer.generation() === generation && !renderer.window.isDestroyed()
        && !event.sender.isDestroyed() && event.sender === renderer.window.webContents
        && frame && !frame.detached && frame === event.sender.mainFrame
        && renderer.policy.allows(frame.url) && renderer.policy.allows(event.sender.getURL()))
    } catch { /* A detached frame may throw while its properties are being read. */ }
    if (!trusted) throw new Error('This request did not come from the trusted application window.')
  }
  assertCurrent()
  return { window: renderer!.window, assertCurrent }
}

export function trustedIpcHandlers(ipc: Pick<IpcMain, 'handle'>, getRenderer: () => TrustedRenderer | undefined) {
  return <Args extends unknown[], Result>(channel: string, handler: (request: TrustedRequest, ...args: Args) => Result) => {
    ipc.handle(channel, async (event, ...args: Args) => {
      const request = authorizeRenderer(event, getRenderer)
      const result = await handler(request, ...args)
      // A picker/backend await may outlive its document, even after a same-URL reload.
      request.assertCurrent()
      return result
    })
  }
}
