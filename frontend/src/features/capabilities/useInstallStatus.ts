import { useEffect, useState } from 'react'
import type { DesktopClient } from '../../services/desktop-client'
import type { InstallStatus } from '../../types/domain'
import { InstallationConnection, type ConnectionState, type InstallTarget } from './installation-connection'

export type Observation = { target: InstallTarget; failure?: unknown }

export function useInstallStatus(client: Pick<DesktopClient, 'getBackendState' | 'onBackendState' | 'getInstallStatus' | 'getActiveInstall'>, observation: Observation | null, received: (status: InstallStatus) => void) {
  const [connection, setConnection] = useState<ConnectionState>({ phase: 'connected', elapsedMs: 0 })
  useEffect(() => {
    if (!observation) return
    // A new operation or explicit retry gets its own observer and deadline.
    // Cleanup invalidates the previous operation's timers and in-flight replies.
    const observer = new InstallationConnection(client, observation.target, setConnection, received)
    observer.start(observation.failure)
    return () => observer.dispose()
  }, [client, observation, received])
  return connection
}
