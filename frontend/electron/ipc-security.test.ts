import { EventEmitter } from 'node:events'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import type { BrowserWindow, IpcMain, IpcMainInvokeEvent } from 'electron'
import { describe, expect, it, vi } from 'vitest'
import { authorizeRenderer, secureRendererWindow, trustedIpcHandlers } from './ipc-security.js'
import { createRendererPolicy, rendererContentSecurityPolicy } from './renderer-policy.js'

const documentPath = path.resolve('fixture café 家庭', 'renderer', 'index.html')
const documentUrl = pathToFileURL(documentPath).href

function fixture() {
  const frame = { url: documentUrl, detached: false }
  const contents = Object.assign(new EventEmitter(), {
    mainFrame: frame, isDestroyed: vi.fn(() => false), getURL: vi.fn(() => frame.url),
    setWindowOpenHandler: vi.fn(),
    session: { setPermissionCheckHandler: vi.fn(), setPermissionRequestHandler: vi.fn() },
  })
  const window = { webContents: contents, isDestroyed: vi.fn(() => false) }
  const renderer = secureRendererWindow(window as unknown as BrowserWindow, createRendererPolicy(documentPath, true))
  const event = { sender: contents, senderFrame: frame } as unknown as IpcMainInvokeEvent
  return { frame, contents, window, renderer, event }
}

describe('renderer document policy', () => {
  const production = createRendererPolicy(documentPath, true)
  it('accepts the exact Unicode document with query parameters and hash routes', () => {
    expect(production.allows(`${documentUrl}?launch=completed#/settings`)).toBe(true)
    expect(production.entryUrl).toBe(documentUrl)
  })
  it.each([
    `${documentUrl}.evil`, pathToFileURL(path.resolve('fixture café 家庭', 'renderer', 'other.html')).href,
    'file://foreign-host/share/index.html', 'file:///C:/Windows/notepad.exe',
    'https://example.invalid/', 'http://localhost:5173/', 'about:blank', 'data:text/html,fixture',
    'not a URL', `${documentUrl.replace('index.html', '%2Findex.html')}`,
  ])('rejects a different document: %s', (url) => expect(production.allows(url)).toBe(false))
  it('ignores even malformed development configuration in a packaged app', () => {
    const policy = createRendererPolicy(documentPath, true, 'not a URL')
    expect(policy.development).toBeNull()
    expect(policy.allows(documentUrl)).toBe(true)
  })
  it('trusts only the selected development endpoint and document', () => {
    const policy = createRendererPolicy(documentPath, false, 'http://127.0.0.1:5173/')
    expect(policy.allows('http://127.0.0.1:5173/?launch=completed#/settings')).toBe(true)
    for (const url of ['http://localhost:5173/', 'http://127.0.0.1:5174/', 'http://127.0.0.1:5173/foreign', documentUrl]) {
      expect(policy.allows(url)).toBe(false)
    }
  })
  it.each(['https://example.invalid/', 'http://127.0.0.1.example.invalid/', 'http://user:pass@localhost:5173/', 'http://localhost:5173/foreign', 'file:///C:/index.html', 'http://127.0.0.1:5174/', 'http://localhost:5173/', 'https://127.0.0.1:5173/'])('rejects unsafe development configuration: %s', (url) => {
    expect(() => createRendererPolicy(documentPath, false, url)).toThrow()
  })
  it('separates production CSP from the exact development HMR endpoint', () => {
    const productionCsp = rendererContentSecurityPolicy()
    expect(productionCsp).toContain("script-src 'self';")
    expect(productionCsp).not.toContain('unsafe-eval')
    expect(productionCsp).toContain("connect-src 'none'")
    expect(productionCsp).toContain("frame-src 'none'")
    const development = rendererContentSecurityPolicy('http://127.0.0.1:5173')
    expect(development).toContain('connect-src http://127.0.0.1:5173 ws://127.0.0.1:5173')
    expect(development).toContain("script-src 'self' 'unsafe-inline'")
  })
})

describe('trusted request lifetime', () => {
  it('allows the live top-level document and its hash navigation', () => {
    const { renderer, event, contents, frame } = fixture()
    const request = authorizeRenderer(event, () => renderer)
    frame.url = `${documentUrl}#/settings`
    contents.emit('did-start-navigation', { isMainFrame: true, isSameDocument: true })
    expect(() => request.assertCurrent()).not.toThrow()
  })
  it.each(['foreign sender', 'child frame', 'null frame', 'detached frame', 'foreign document', 'destroyed window', 'destroyed contents'])('rejects %s before dispatch', (condition) => {
    const { renderer, event, contents, window, frame } = fixture()
    const changed = { ...event }
    if (condition === 'foreign sender') changed.sender = { ...contents } as unknown as typeof event.sender
    if (condition === 'child frame') changed.senderFrame = { ...frame } as typeof event.senderFrame
    if (condition === 'null frame') changed.senderFrame = null
    if (condition === 'detached frame') frame.detached = true
    if (condition === 'foreign document') frame.url = 'https://example.invalid/'
    if (condition === 'destroyed window') window.isDestroyed.mockReturnValue(true)
    if (condition === 'destroyed contents') contents.isDestroyed.mockReturnValue(true)
    expect(() => authorizeRenderer(changed, () => renderer)).toThrow('trusted application window')
  })
  it('invalidates an awaited picker after a same-URL reload or window replacement', () => {
    const { renderer, event, contents } = fixture()
    const request = authorizeRenderer(event, () => renderer)
    contents.emit('did-start-navigation', { isMainFrame: true, isSameDocument: false })
    expect(() => request.assertCurrent()).toThrow()
    const current = { renderer: renderer as typeof renderer | undefined }
    const second = authorizeRenderer(event, () => current.renderer)
    current.renderer = undefined
    expect(() => second.assertCurrent()).toThrow()
  })
  it('guards registered actions before execution and before returning an awaited result', async () => {
    const { renderer, event, contents, frame } = fixture()
    const handle = vi.fn()
    const action = vi.fn(async () => 'selected path')
    trustedIpcHandlers({ handle } as unknown as Pick<IpcMain, 'handle'>, () => renderer)('picker', action)
    const callback = handle.mock.calls[0][1]
    frame.url = 'https://example.invalid'
    await expect(callback(event)).rejects.toThrow('trusted application window')
    expect(action).not.toHaveBeenCalled()
    frame.url = documentUrl
    action.mockImplementation(async () => {
      contents.emit('did-start-navigation', { isMainFrame: true, isSameDocument: false })
      return 'selected path'
    })
    await expect(callback(event)).rejects.toThrow('trusted application window')
  })
})

describe('window restrictions', () => {
  it.each(['will-navigate', 'will-frame-navigate', 'will-redirect'])('blocks foreign %s', (eventName) => {
    const { contents } = fixture()
    const event = { url: 'https://example.invalid/', isMainFrame: true, preventDefault: vi.fn() }
    contents.emit(eventName, event)
    expect(event.preventDefault).toHaveBeenCalledOnce()
  })
  it('denies child navigation, popups, and browser permissions', () => {
    const { contents } = fixture()
    const event = { url: documentUrl, isMainFrame: false, preventDefault: vi.fn() }
    contents.emit('will-frame-navigate', event)
    expect(event.preventDefault).toHaveBeenCalledOnce()
    expect(contents.setWindowOpenHandler.mock.calls[0][0]({})).toEqual({ action: 'deny' })
    expect(contents.session.setPermissionCheckHandler.mock.calls[0][0]()).toBe(false)
    const callback = vi.fn()
    contents.session.setPermissionRequestHandler.mock.calls[0][0](contents, 'media', callback)
    expect(callback).toHaveBeenCalledWith(false)
  })
})
