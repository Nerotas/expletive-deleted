import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readyCapabilities } from '../test/fixtures'
import type { SystemCheck } from '../types/domain'
import { decodeSystemCheck, observeSystemCheck } from './system-check'

const running: SystemCheck = { check_id: 'one', status: 'running', stage: 'speech_model', elapsed_ms: 0,
  stage_elapsed_ms: 0, timings: {}, capabilities: null, error: null }
const completed: SystemCheck = { ...running, status: 'completed', elapsed_ms: 70000,
  timings: { speech_model: 70000 }, capabilities: { ...readyCapabilities, processing_ready: true } }

describe('system-check observer protocol', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())
  it('polls status after 60 seconds without restarting the original probe', async () => {
    const start = vi.fn(async () => running)
    const status = vi.fn(async (): Promise<SystemCheck> => running)
    const progress = vi.fn()
    const pending = observeSystemCheck(start, status, progress)
    await vi.advanceTimersByTimeAsync(65000)
    expect(start).toHaveBeenCalledOnce()
    expect(status.mock.calls.length).toBeGreaterThan(60)
    status.mockResolvedValueOnce(completed)
    await vi.advanceTimersByTimeAsync(1000)
    expect(await pending).toEqual(completed.capabilities)
    expect(progress).toHaveBeenLastCalledWith(completed)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('bounds a missing status reply and recovers a finished check on reconnect', async () => {
    const start = vi.fn(async (): Promise<SystemCheck> => running)
    const status = vi.fn(() => new Promise(() => {}))
    const pending = observeSystemCheck(start, status).catch((error) => error)
    await vi.advanceTimersByTimeAsync(3000)
    expect(await pending).toMatchObject({ code: 'request_timeout' })
    start.mockResolvedValueOnce(completed)
    expect(await observeSystemCheck(start, status)).toEqual(completed.capabilities)
    expect(status).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('cancels observation and leaves no polling timers behind', async () => {
    const controller = new AbortController()
    const pending = observeSystemCheck(async () => running, async () => running, undefined, controller.signal).catch((error) => error)
    await vi.advanceTimersByTimeAsync(0)
    controller.abort()
    expect(await pending).toMatchObject({ name: 'AbortError' })
    expect(vi.getTimerCount()).toBe(0)
  })
  it.each([
    { ...running, elapsed_ms: Infinity }, { ...running, timings: { unknown: 1 } },
    { ...running, capabilities: readyCapabilities }, { ...completed, capabilities: null },
    { ...running, stage: 'unknown' }, { ...running, check_id: '' },
  ])('rejects invalid readiness/progress envelopes', (value) => {
    expect(() => decodeSystemCheck(value)).toThrow('invalid verification status')
  })
})
