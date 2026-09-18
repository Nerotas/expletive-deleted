// Run from frontend/. Execute the actual transport source with mocked Electron.
const path = require('node:path')
const { transformSync } = require(path.resolve('node_modules/esbuild'))
const { readFileSync } = require('node:fs')
const { EventEmitter } = require('node:events')
const vm = require('node:vm')

const child = new EventEmitter()
child.stdin = { writable: true, write: (_text, callback) => callback(null) }
child.stdout = new EventEmitter()
child.stderr = new EventEmitter()
const app = new EventEmitter()
Object.assign(app, { whenReady: () => Promise.resolve(), isPackaged: false, getAppPath: () => '.', setAppUserModelId() {} })
class BrowserWindow extends EventEmitter { loadFile() { return Promise.resolve() } }
const source = readFileSync('electron/main.ts', 'utf8') + '\nglobalThis.audit = { invoke, pending };'
const code = transformSync(source, { loader: 'ts', format: 'cjs' }).code
const context = vm.createContext({
  require: name => {
    if (name === 'electron') return { app, BrowserWindow, ipcMain: { handle() {} }, Menu: { setApplicationMenu() {} } }
    if (name === 'node:child_process') return { spawn: () => child }
    if (name === './backend-runtime.js') return { backendEnvironment: () => ({}), findBackendRoot: () => '.', findPythonRuntime: () => ({ command: 'fake', args: [] }) }
    if (name === './bridge-shutdown.js') return { stopBridge: async () => {} }
    return require(name)
  },
  process: { env: {}, platform: 'win32', resourcesPath: '.', cwd: () => '.' },
  __dirname: path.resolve('out/main'), console, setTimeout, clearTimeout,
})
vm.runInContext(code, context)
setImmediate(async () => {
  let malformedSettled = false, missingSettled = false, rawExitMessage
  const first = context.audit.invoke('settings.get').then(() => { malformedSettled = true }, () => { malformedSettled = true })
  child.stdout.emit('data', Buffer.from('{"id":1,"ok":false}\n'))
  const removedFromPending = !context.audit.pending.has(1)
  context.audit.invoke('settings.get').then(() => { missingSettled = true }, error => { missingSettled = true; rawExitMessage = error.message })
  child.stdout.emit('data', Buffer.from('invalid response\n'))
  await new Promise(resolve => setTimeout(resolve, 100))
  const pendingBeforeExit = context.audit.pending.size
  child.stderr.emit('data', Buffer.from('simulated sensitive transcript diagnostic'))
  child.emit('exit', 1)
  await new Promise(resolve => setImmediate(resolve))
  console.log(JSON.stringify({ malformedResponse: { removedFromPending, settledEvenAfterExit: malformedSettled }, invalidResponse: { pendingBeforeExit, settledOnExit: missingSettled }, rawExitMessage }))
})
