import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import path from 'node:path'

// Exercise the real preload and ipcMain registrations; stub only OS side effects.
export async function assertRendererSecurity(app, page, { development = false } = {}) {
  const entryUrl = page.url()
  const redirectRequests = { started: 0, followed: 0 }
  const server = createServer((request, response) => {
    if (request.url === '/redirect') {
      redirectRequests.started += 1
      response.writeHead(302, { Location: '/redirect-target' }).end()
    } else {
      if (request.url === '/redirect-target') redirectRequests.followed += 1
      response.setHeader('Content-Type', 'text/html')
      response.end('<!doctype html><title>Untrusted security fixture</title>')
    }
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const foreignUrl = `http://127.0.0.1:${server.address().port}/foreign`
  const mainId = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].id)
  await app.evaluate(({ BrowserWindow, shell, dialog }, id) => {
    const window = BrowserWindow.fromId(id)
    globalThis.__securitySmoke = {
      calls: [], window,
      originals: { openPath: shell.openPath, openExternal: shell.openExternal,
        showOpenDialog: dialog.showOpenDialog, showSaveDialog: dialog.showSaveDialog },
    }
    shell.openPath = async (value) => { globalThis.__securitySmoke.calls.push(['path', value]); return '' }
    shell.openExternal = async (value) => { globalThis.__securitySmoke.calls.push(['external', value]) }
    dialog.showOpenDialog = async () => {
      globalThis.__securitySmoke.calls.push(['open-dialog'])
      return { canceled: true, filePaths: [] }
    }
    dialog.showSaveDialog = async () => {
      globalThis.__securitySmoke.calls.push(['save-dialog'])
      return { canceled: true }
    }
  }, mainId)

  // Restart is tested only from hostile documents here; recovery smoke exercises
  // the explicit authorized restart without interrupting these boundary checks.
  const exerciseChannels = (target, hostile = false) => target.evaluate(async (hostile) => {
    const api = window.expletiveDeleted
    const requests = [
      () => api.invoke('settings.get'), () => api.selectDirectory(), () => api.selectFile(),
      () => api.importDictionary(), () => api.exportDictionary(),
      () => api.openExternal('https://example.invalid/security-fixture'),
      () => api.openTranscodeFolder(), () => api.openOutput('security-fixture.txt'),
      () => api.request('settings.get'), () => api.getBackendState(),
      ...(hostile ? [() => api.restart()] : []),
    ]
    const results = []
    for (const request of requests) {
      try { await request(); results.push('allowed') } catch (error) { results.push(error.message) }
    }
    return results
  }, hostile)
  const assertDenied = (results) => {
    assert.equal(results.length, 11)
    for (const result of results) assert.match(result, /trusted application window/)
  }

  try {
    const preferences = await app.evaluate(() => {
      const prefs = globalThis.__securitySmoke.window.webContents.getLastWebPreferences()
      return { sandbox: prefs.sandbox, contextIsolation: prefs.contextIsolation, nodeIntegration: prefs.nodeIntegration }
    })
    assert.deepEqual(preferences, { sandbox: true, contextIsolation: true, nodeIntegration: false })
    assert.equal(await page.evaluate(() => typeof window.require), 'undefined')
    assert.deepEqual(await page.evaluate(() => Object.keys(window.expletiveDeleted).sort()), [
      'desktop', 'invoke', 'request', 'getBackendState', 'onBackendState', 'restart',
      'selectDirectory', 'selectFile', 'importDictionary', 'exportDictionary',
      'openExternal', 'openTranscodeFolder', 'openOutput', 'getPathForFile',
    ].sort(), 'Packaged and development preload must expose no fixture controls')
    const csp = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content')
    assert.ok(csp)
    assert.ok(!csp.includes('unsafe-eval'))
    assert.ok(csp.includes("frame-src 'none'"))
    if (!development) {
      assert.ok(csp.includes("script-src 'self';"))
      assert.ok(csp.includes("connect-src 'none'"))
      const violations = await page.evaluate(async (url) => {
        const directives = []
        const listener = (event) => directives.push(event.effectiveDirective)
        document.addEventListener('securitypolicyviolation', listener)
        const script = document.createElement('script')
        script.textContent = 'window.__unexpectedInlineExecution = true'
        document.head.append(script)
        const iframe = document.createElement('iframe')
        iframe.src = url
        document.body.append(iframe)
        const fetched = await fetch(url).then(() => true, () => false)
        // CSP violation events are queued after the blocked operation.
        await new Promise((resolve, reject) => {
          const deadline = Date.now() + 5000
          const check = () => {
            if (directives.length >= 3) resolve()
            else if (Date.now() > deadline) reject(new Error(`Missing CSP violations: ${directives}`))
            else setTimeout(check, 10)
          }
          check()
        })
        document.removeEventListener('securitypolicyviolation', listener)
        script.remove()
        iframe.remove()
        return { directives, fetched, ran: window.__unexpectedInlineExecution === true }
      }, foreignUrl)
      assert.equal(violations.ran, false)
      assert.equal(violations.fetched, false)
      for (const directive of ['script-src-elem', 'connect-src', 'frame-src']) {
        assert.ok(violations.directives.includes(directive), `Missing CSP enforcement: ${directive}`)
      }
    }

    console.log('Checking authorized IPC channels')
    const trustedResults = await exerciseChannels(page)
    assert.deepEqual(trustedResults.slice(0, 7), Array(7).fill('allowed'))
    assert.match(trustedResults[7], /absolute path/)
    assert.deepEqual(trustedResults.slice(8), ['allowed', 'allowed'])
    for (const method of ['dictionary.import', 'dictionary.export', 'native.output.prepare', 'native.output.check', 'native.export.prepare', 'native.dictionary.export', 'native.dictionary.import', 'native.release', 'test.silence', 'test.exit', 'dependencies.test_silence']) {
      await assert.rejects(page.evaluate((method) => window.expletiveDeleted.invoke(method, {}), method), /approved native file selection/)
    }
    assert.equal(await app.evaluate(() => globalThis.__securitySmoke.calls.length), 6)
    await assert.rejects(page.evaluate(() => window.expletiveDeleted.openExternal('http://example.invalid/')), /secure project links/)

    // Observe the prevention event instead of relying on a timing delay.
    await app.evaluate(() => {
      globalThis.__securitySmoke.navigation = new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(false), 5000)
        globalThis.__securitySmoke.window.webContents.once('will-frame-navigate', (event) => { clearTimeout(timeout); resolve(event.defaultPrevented) })
      })
    })
    await page.evaluate((url) => { window.location.assign(url) }, foreignUrl)
    assert.equal(await app.evaluate(() => globalThis.__securitySmoke.navigation), true)
    assert.equal(page.url(), entryUrl)
    assert.equal(await page.evaluate((url) => window.open(url) === null, foreignUrl), true)
    assert.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length), 1)

    console.log('Checking foreign documents and redirected navigation')
    // Main-process loads deliberately bypass will-navigate, proving IPC has its own guard.
    await app.evaluate(async (_, url) => { await globalThis.__securitySmoke.window.loadURL(url) }, foreignUrl)
    assertDenied(await exerciseChannels(page, true))
    // Keep the inert fixture loaded: reloading React here lets HashRouter's
    // initial replaceState interrupt loadURL before the HTTP request even starts.
    await app.evaluate(async (_, url) => {
      const contents = globalThis.__securitySmoke.window.webContents
      const events = []
      let redirect
      const observers = new Map()
      for (const name of ['will-redirect', 'did-fail-load', 'did-start-navigation', 'did-navigate-in-page']) {
        const observe = (event, ...args) => {
          events.push({ name, url: event.url, prevented: event.defaultPrevented, args })
          if (name === 'will-redirect') {
            redirect = { url: event.url, mainFrame: event.isMainFrame, prevented: event.defaultPrevented }
          }
        }
        observers.set(name, observe)
        contents.on(name, observe)
      }
      try {
        let error
        await contents.loadURL(url).catch((reason) => { error = reason.message })
        globalThis.__securitySmoke.redirectResult = { redirect, error, events }
      } finally {
        for (const [name, observe] of observers) contents.removeListener(name, observe)
      }
    }, foreignUrl.replace('/foreign', '/redirect'))
    const redirectResult = await app.evaluate(() => globalThis.__securitySmoke.redirectResult)
    const diagnostic = JSON.stringify({ requests: redirectRequests, ...redirectResult })
    // A generic load failure is insufficient: prove the actual guard ran and the
    // forbidden destination was never fetched, even if loadURL rejects with ERR_FAILED.
    assert.deepEqual(redirectResult.redirect, {
      url: foreignUrl.replace('/foreign', '/redirect-target'), mainFrame: true, prevented: true,
    }, diagnostic)
    assert.deepEqual(redirectRequests, { started: 1, followed: 0 }, diagnostic)
    await app.evaluate(async (_, url) => { await globalThis.__securitySmoke.window.loadURL(url) }, entryUrl)

    // Even another window showing the exact trusted document must have no native authority.
    const extraPagePromise = app.waitForEvent('window')
    const preload = path.join(await app.evaluate(({ app }) => app.getAppPath()), 'out', 'preload', 'preload.cjs')
    await app.evaluate(async ({ BrowserWindow }, { url, preload }) => {
      const extra = new BrowserWindow({ show: false, webPreferences: { preload, sandbox: true, contextIsolation: true, nodeIntegration: false } })
      globalThis.__securitySmoke.extra = extra
      await extra.loadURL(url)
    }, { url: entryUrl, preload })
    const extraPage = await extraPagePromise
    await extraPage.waitForLoadState('domcontentloaded')
    assertDenied(await exerciseChannels(extraPage, true))
    assert.equal(await app.evaluate(() => globalThis.__securitySmoke.calls.length), 6)
    console.log(`Renderer security checks passed (${development ? 'Vite development' : 'production'}): all 10 IPC channels (11 preload operations), CSP, sandbox, navigation, redirects, popups, foreign documents and windows.`)
  } finally {
    await app.evaluate(({ shell, dialog }) => {
      const state = globalThis.__securitySmoke
      state.extra?.destroy()
      Object.assign(shell, { openPath: state.originals.openPath, openExternal: state.originals.openExternal })
      Object.assign(dialog, { showOpenDialog: state.originals.showOpenDialog, showSaveDialog: state.originals.showSaveDialog })
      delete globalThis.__securitySmoke
    })
    server.closeAllConnections()
    await new Promise((resolve) => server.close(resolve))
  }
}
