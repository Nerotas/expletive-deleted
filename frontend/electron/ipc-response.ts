export type InvokeResponse<T> = { result: T } | { error: { message: string; code?: string; diagnostic?: string } }

export async function respond<T>(operation: () => Promise<T>): Promise<InvokeResponse<T>> {
  try { return { result: await operation() } } catch (reason) {
    const error = reason as Error & { code?: unknown; diagnostic?: unknown }
    return { error: {
      message: error instanceof Error ? error.message : 'The local processing service rejected the request.',
      ...(typeof error.code === 'string' ? { code: error.code } : {}),
      ...(typeof error.diagnostic === 'string' ? { diagnostic: error.diagnostic } : {}),
    } }
  }
}

export function unwrapInvokeResponse<T>(response: InvokeResponse<T>): T {
  if ('result' in response) return response.result
  const error = Object.assign(
    new Error(response.error.message),
    response.error.code ? { code: response.error.code } : {},
    response.error.diagnostic ? { diagnostic: response.error.diagnostic } : {},
  )
  throw error
}
