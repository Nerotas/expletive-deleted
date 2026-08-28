import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { lib: { entry: 'electron/main.ts' }, rollupOptions: { output: { format: 'cjs', entryFileNames: '[name].cjs' } } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: { lib: { entry: 'electron/preload.ts' }, rollupOptions: { output: { format: 'cjs', entryFileNames: '[name].cjs' } } },
  },
  renderer: {
    root: '.',
    plugins: [react()],
    build: { rollupOptions: { input: resolve(__dirname, 'index.html') } },
  },
})
