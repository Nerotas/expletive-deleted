import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import { DEVELOPMENT_HOST, DEVELOPMENT_PORT, rendererContentSecurityPolicy } from './electron/renderer-policy.js'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { lib: { entry: 'electron/main.ts' }, rollupOptions: { output: { format: 'cjs', entryFileNames: '[name].cjs' } } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    // Sandboxed preload only requires Electron; local helpers must remain in this bundle.
    build: { lib: { entry: 'electron/preload.ts' }, rollupOptions: { output: { format: 'cjs', entryFileNames: '[name].cjs', inlineDynamicImports: true } } },
  },
  renderer: {
    root: '.',
    server: {
      host: DEVELOPMENT_HOST, port: DEVELOPMENT_PORT, strictPort: true,
      // Private runtimes and packaged copies are not renderer development sources.
      watch: { ignored: ['**/release/**', '**/runtime/**'] },
    },
    plugins: [react(), {
      name: 'renderer-content-security-policy',
      transformIndexHtml: {
        order: 'post',
        handler: (_html, context) => [{
          tag: 'meta',
          attrs: {
            'http-equiv': 'Content-Security-Policy',
            content: rendererContentSecurityPolicy(context.server ? `http://${DEVELOPMENT_HOST}:${DEVELOPMENT_PORT}` : undefined),
          },
          injectTo: 'head-prepend',
        }],
      },
    }],
    build: { rollupOptions: { input: resolve(__dirname, 'index.html') } },
  },
})
