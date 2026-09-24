import { expect, it } from 'vitest'
import { decodeInstallStatus } from './install-status'
import { running } from '../test/install-fixtures'

it.each([null, {}, { ...running, status: 'success' }, { ...running, completed_bytes: '100' }, { ...running, status: 'awaiting_resolution', resolution: {} }])('classifies incompatible setup payloads without claiming success: %j', (value) => {
  expect(() => decodeInstallStatus(value)).toThrow(expect.objectContaining({ code: 'protocol_error' }))
})
