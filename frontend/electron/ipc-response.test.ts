import { describe, expect, it } from 'vitest'
import { unwrapInvokeResponse, type InvokeResponse } from './ipc-response.js'

describe('IPC response handling', () => {
  it.each([null, {}, { result: true, error: { message: 'conflicting' } }, { error: {} }])('rejects malformed native envelopes: %j', (response) => {
    expect(() => unwrapInvokeResponse(response as InvokeResponse<unknown>)).toThrow(expect.objectContaining({ code: 'protocol_error' }))
  })
  it('preserves a structured backend error code', () => {
    try {
      unwrapInvokeResponse({
        error: {
          message: 'YouTube requires authentication or verification',
          code: 'authentication_required',
        },
      })
      throw new Error('Expected unwrapInvokeResponse to throw')
    } catch (reason) {
      expect(reason).toMatchObject({
        message: 'YouTube requires authentication or verification',
        code: 'authentication_required',
      })
    }
  })

  it('preserves the raw diagnostic detail behind a classified error', () => {
    try {
      unwrapInvokeResponse({
        error: {
          message: 'The selected browser session could not be read',
          code: 'browser_cookies_unavailable',
          diagnostic: 'ERROR: Could not copy Chrome cookie database',
        },
      })
      throw new Error('Expected unwrapInvokeResponse to throw')
    } catch (reason) {
      expect(reason).toMatchObject({
        message: 'The selected browser session could not be read',
        code: 'browser_cookies_unavailable',
        diagnostic: 'ERROR: Could not copy Chrome cookie database',
      })
    }
  })
})
