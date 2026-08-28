# Profanity Censor Desktop

Electron hosts the React renderer in this directory. This is an installed desktop application, not a browser-hosted application.

From `frontend/`:

```powershell
npm install
npm run dev
```

`npm run dev` launches Electron. Vite is used only as Electron's renderer build and hot-reload tool.

Production validation:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
npm run smoke
```

## Renderer architecture

- `src/App.tsx` composes the shell, global status, and routes.
- `src/features/` owns Queue, Dictionary, Settings, and capability state.
- `src/components/ui/` contains reusable controls and presentation primitives.
- `src/services/desktop-client.ts` is the typed boundary around Electron IPC.
- React Router handles renderer navigation, TanStack Query owns backend state, and React Hook Form owns the persisted/draft settings lifecycle.
