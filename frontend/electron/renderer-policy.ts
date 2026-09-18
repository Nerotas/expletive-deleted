import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export const DEVELOPMENT_HOST = '127.0.0.1'
export const DEVELOPMENT_PORT = 5173

export function developmentRendererUrl(value: string): URL {
  const url = new URL(value)
  if (url.origin !== `http://${DEVELOPMENT_HOST}:${DEVELOPMENT_PORT}`
    || url.username || url.password || url.search || url.hash
    || !['/', '/index.html'].includes(url.pathname)) {
    throw new Error('The development renderer must use a local Vite document.')
  }
  return url
}

export function createRendererPolicy(documentPath: string, isPackaged: boolean, developmentUrl?: string) {
  // Installed applications never trust a renderer URL supplied by the environment.
  const development = !isPackaged && developmentUrl ? developmentRendererUrl(developmentUrl) : null
  const normalizePath = (value: string) => {
    const normalized = path.resolve(value)
    return process.platform === 'win32' ? normalized.toLowerCase() : normalized
  }
  const expectedPath = normalizePath(documentPath)
  return {
    development,
    entryUrl: development?.href ?? pathToFileURL(documentPath).href,
    allows(value: string): boolean {
      try {
        const url = new URL(value)
        if (url.username || url.password) return false
        if (development) return url.origin === development.origin && url.pathname === development.pathname
        // Query parameters and hash routes do not change which bundled document runs.
        return url.protocol === 'file:' && !url.hostname
          && normalizePath(fileURLToPath(url)) === expectedPath
      } catch {
        return false
      }
    },
  }
}

export type RendererPolicy = ReturnType<typeof createRendererPolicy>

export function rendererContentSecurityPolicy(developmentOrigin?: string): string {
  const origin = developmentOrigin ? developmentRendererUrl(developmentOrigin).origin : null
  const socket = origin?.replace(/^http/, 'ws')
  return [
    "default-src 'self'",
    // Vite's React refresh preamble is inline only in development; production has no inline scripts.
    `script-src 'self'${origin ? " 'unsafe-inline'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data:",
    `connect-src ${origin ? `${origin} ${socket}` : "'none'"}`,
    "object-src 'none'",
    "frame-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ')
}
