import { vi } from 'vitest'
import type { BackendState } from '../../shared/bridge'
import type { InstallStatus } from '../types/domain'
import { InstallationConnection } from '../features/capabilities/installation-connection'

export const running: InstallStatus = { install_id: 'one', status: 'running', message: 'Installing model', action_id: null, action_index: null, action_count: null, phase: 'running', completed_bytes: null, total_bytes: null, started_at: null, error: null }
export function fixture() {
  let listener: (value: BackendState) => void = () => {}
  const unsubscribe = vi.fn()
  const client = {
    getBackendState: vi.fn(async (): Promise<BackendState> => ({ generation: 1, status: 'running' })),
    onBackendState: vi.fn((fn: typeof listener) => { listener = fn; return unsubscribe }),
    getInstallStatus: vi.fn(async () => running),
    getActiveInstall: vi.fn(async (): Promise<InstallStatus | null> => running),
  }
  const changed = vi.fn(), received = vi.fn()
  const observer = new InstallationConnection(client, { installId: 'one' }, changed, received)
  return { client, changed, received, observer, unsubscribe, event: (state: BackendState) => listener(state) }
}

