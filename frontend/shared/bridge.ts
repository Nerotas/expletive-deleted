export type BackendState = { generation: number; status: 'running' | 'exited' | 'unavailable' }
export type RequestOptions = { timeoutMs?: number; generation?: number }
