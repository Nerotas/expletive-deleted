import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'
import { builtinModules } from 'node:module'

export default defineConfig([
  globalIgnores(['dist', 'out', 'test-results']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      // Native capabilities belong to Electron, never to renderer feature modules.
      'no-restricted-imports': ['error', {
        paths: [...new Set(['electron', ...builtinModules.flatMap((name) => [name, name.startsWith('node:') ? name : `node:${name}`])])],
        patterns: ['**/electron/**'],
      }],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/services/desktop-client.ts', 'src/**/*.test.{ts,tsx}', 'src/**/*.d.ts', 'src/test/**'],
    rules: {
      'no-restricted-syntax': ['error', {
        selector: 'MemberExpression[property.name="expletiveDeleted"], MemberExpression[property.value="expletiveDeleted"]',
        message: 'Use services/desktop-client.ts instead of accessing the preload bridge directly.',
      }],
    },
  },
])
