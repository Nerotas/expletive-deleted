export type InvokeResponse<T> = { result: T } | { error: { message: string; code?: string; diagnostic?: string } }

export function unwrapInvokeResponse<T>(response: InvokeResponse<T>): T {
  if ('result' in response) return response.result
  const error = Object.assign(
    new Error(response.error.message),
    response.error.code ? { code: response.error.code } : {},
    response.error.diagnostic ? { diagnostic: response.error.diagnostic } : {},
  )
  throw error
}