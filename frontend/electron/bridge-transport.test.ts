// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BridgeTransport } from './bridge-transport.js'

describe('bridge transport', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())
  function setup() {
    const write = vi.fn((_line: string, done: (error?: Error) => void) => done())
    const publish = vi.fn()
    const bridge = new BridgeTransport(3, write, publish)
    return { bridge, write, publish, reply: (value: unknown) => bridge.receive(Buffer.from(JSON.stringify(value) + '\n')) }
  }
  it('removes timed-out reads, ignores late replies, and never replays commands', async () => {
    const { bridge, reply, write } = setup()
    const pending = bridge.request('dependencies.status').catch((error) => error)
    await vi.advanceTimersByTimeAsync(1999)
    expect(bridge.pendingCount).toBe(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(await pending).toMatchObject({ code: 'request_timeout' })
    expect(bridge.pendingCount).toBe(0)
    const next = bridge.request('dependencies.install')
    reply({ id: 1, ok: true, result: 'old' })
    expect(bridge.pendingCount).toBe(1)
    reply({ id: 2, ok: true, result: 'current' })
    expect(await next).toBe('current')
    expect(write).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })
  it.each([
    { id: 1, ok: true }, { id: 1, ok: false }, { id: 1, ok: false, error: { message: 9 } },
    { id: 1, ok: true, result: {}, error: {} }, { id: 1, ok: false, error: { message: 'bad', code: {} } },
  ])('rejects malformed identified envelopes before discarding pending requests: %j', async (value) => {
    const { bridge, reply } = setup()
    const pending = bridge.request('dependencies.status').catch((error) => error)
    reply(value)
    expect(await pending).toMatchObject({ code: 'protocol_error' })
    expect(bridge.pendingCount).toBe(0)
  })
  it('decodes partial lines and split UTF-8 characters', async () => {
    const { bridge } = setup()
    const pending = bridge.request('settings.get')
    const line = Buffer.from('{"id":1,"ok":true,"result":"café"}\n')
    for (const byte of line) bridge.receive(Buffer.from([byte]))
    expect(await pending).toBe('café')
  })
  it('classifies exits, pipe loss and obsolete generations without leaking timers', async () => {
    const { bridge, publish, write } = setup()
    await expect(bridge.request('dependencies.status', {}, { generation: 2 })).rejects.toMatchObject({ code: 'backend_changed' })
    expect(write).not.toHaveBeenCalled()
    const pending = bridge.request('dependencies.cancel').catch((error) => error)
    bridge.stop('exited')
    expect(await pending).toMatchObject({ code: 'backend_exited' })
    expect(publish).toHaveBeenCalledWith({ generation: 3, status: 'exited' })
    expect(vi.getTimerCount()).toBe(0)
    await expect(bridge.request('dependencies.active')).rejects.toMatchObject({ code: 'backend_exited' })
  })
  it('caps client deadlines and reports pipe failures', async () => {
    const { bridge, write } = setup()
    const pending = bridge.request('dependencies.status', {}, { timeoutMs: 1e9 }).catch((error) => error)
    await vi.advanceTimersByTimeAsync(2000)
    expect(await pending).toMatchObject({ code: 'request_timeout' })
    write.mockImplementationOnce((_line, done) => done(new Error('pipe closed')))
    await expect(bridge.request('dependencies.status')).rejects.toMatchObject({ code: 'backend_unavailable' })
  })
  it('does not impose the setup deadline on long media mutations', async () => {
    const { bridge, reply, write } = setup()
    const pending = bridge.request('library.import')
    await vi.advanceTimersByTimeAsync(120_000)
    expect(bridge.pendingCount).toBe(1)
    expect(write).toHaveBeenCalledOnce()
    reply({ id: 1, ok: true, result: [] })
    expect(await pending).toEqual([])
  })
})
