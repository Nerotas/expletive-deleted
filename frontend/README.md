# Expletive Deleted Desktop

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
npm run package:dir
npm run smoke:package
npm run package:win
```

`package:dir` creates `release/win-unpacked` for packaged-runtime testing. `package:win` creates the assisted x64 NSIS installer in `release/`. The package contains Electron and first-party Python sources only; required third-party runtimes and models remain under the explicit setup policy. The installed app locates Python 3.9+ through `CENSOR_PYTHON`, the Windows `py` launcher, or `python`.

The Windows package wrapper cleans incomplete generated staging directories and retries Electron Builder's transient `EPERM` rename failure up to three times. If cleanup remains locked, close any packaged Expletive Deleted process and Explorer window open to `frontend/release`, then run the command again.

Both package commands audit `win-unpacked` and fail if it contains `ffmpeg.exe`, `ffprobe.exe`, Whisper model payloads, or Python binary packages. Electron's single root `ffmpeg.dll` is framework-owned Chromium codec support and is the only allowed FFmpeg-named binary in the installer.

## Renderer architecture

- `src/App.tsx` composes the shell, global status, and routes.
- `src/features/` owns Queue, Dictionary, Settings, and capability state.
- `src/components/ui/` contains reusable controls and presentation primitives.
- `src/services/desktop-client.ts` is the typed boundary around Electron IPC.
- React Router handles renderer navigation, TanStack Query owns backend state, and React Hook Form owns the persisted/draft settings lifecycle.

## Queue behavior

- Each file exposes **Transcribe only**, **Transcribe + Transcode**, and guarded **Archive** actions.
- Ready-file checkboxes submit an exact ordered selection through the typed `jobs.submit_many` bridge operation.
- The table can filter Ready, Queued, Active, Transcribed, and Finished rows and sort by queue position, file name, or status.
- Waiting jobs show their position and can be removed independently; the running job can be cancelled from its row or the top-level cancel action.
- The renderer never decides that a transcript is safe for transcoding. That mandatory persisted-artifact gate belongs to the Python backend.

## Dictionary behavior

- The resource text files are built-in defaults and are never edited by the renderer.
- The live policy uses backend-managed `censored.json`, `exclusions.json`, and `discovered.json` stores beneath `%LOCALAPPDATA%\ExpletiveDeleted\dictionary`.
- Import, export, validation, and restore-defaults behavior remain backend-owned. Combined JSON is only the explicit portable format. Restore requires explicit renderer confirmation.

Electron uses the `com.expletive-deleted.desktop` Windows AppUserModelID, private `expletive-deleted:*` IPC channels, and the narrow typed `window.expletiveDeleted` preload API.

- The Dictionary displays the durable user path and policy metadata; processing loads the same complete policy at job start.
