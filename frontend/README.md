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
npm run typecheck
npm run lint
npm run build
```
