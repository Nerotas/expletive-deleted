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
..\scripts\build_local_release.ps1
```

The local release command runs the same validation and audited installer stages as the GitHub release workflow. It accepts Node.js 22.12.0 or later and obtains the checksum-verified Python 3.13.15 runtime automatically when needed. The installer contains the application and private Python payload; FFmpeg/FFprobe, yt-dlp, Deno, Python packages, and the selected Whisper model are verified or obtained through explicit onboarding setup. Whisper models remain user-selected and are never bundled.

The Windows package wrapper cleans incomplete generated staging directories and retries Electron Builder's transient `EPERM` rename failure up to three times. If cleanup remains locked, close any packaged Expletive Deleted process and Explorer window open to `frontend/release`, then run the command again.

The package audit requires private Python and rejects processing packages, FFmpeg/FFprobe executables and libraries, yt-dlp, Deno, Whisper model payloads, and accidental development binaries. Electron's single root `ffmpeg.dll` remains framework-owned Chromium codec support and must not satisfy the application's FFmpeg readiness check.

## Renderer architecture

- `src/App.tsx` composes the shell, global status, and routes.
- `src/features/` owns Queue, Dictionary, Settings, Onboarding, and capability state.
- `src/features/onboarding/` keeps each walkthrough section in its own component: Welcome, Components, Initial Settings, Add Media, Process Media, Finish, and backend-startup recovery. `OnboardingPage.tsx` owns only composition, saved-step navigation, and the temporary settings draft.
- `src/components/ui/` contains reusable controls and presentation primitives.
- `src/services/desktop-client.ts` is the typed boundary around Electron IPC.
- React Router handles renderer navigation, TanStack Query owns backend state, and React Hook Form owns the persisted/draft settings lifecycle.

## Queue behavior

- Each local file exposes **Transcribe** or **Retranscribe** and guarded **Archive** actions. Archive requires a verified transcript or output and no queued or active job for that source; unrelated jobs do not block it. Censor submission is available in bulk from the Transcribed filter.
- Ready-file checkboxes submit transcript jobs; Transcribed-file checkboxes submit an exact ordered censor selection through the typed `jobs.submit_many` bridge operation.
- The table can filter Ready, Queued, Active, Transcribed, and Finished rows and sort by queue position, file name, or status.
- Waiting jobs show their position and can be removed independently; the running job can be cancelled from its row or the top-level cancel action.
- The optional persisted setting `processing.auto_censor_after_transcription` promotes each newly verified transcript to the censored-copy queue. `processing.auto_transcode_youtube_downloads` starts the same chain after a completed YouTube download.
- The renderer never decides that a transcript is safe for transcoding. That mandatory persisted-artifact gate belongs to the Python backend.

## Dictionary behavior

- The resource text files are built-in defaults and are never edited by the renderer.
- The live policy uses backend-managed `censored.json`, `exclusions.json`, and `discovered.json` stores beneath `%LOCALAPPDATA%\ExpletiveDeleted\dictionary`.
- Import, export, validation, and restore-defaults behavior remain backend-owned. Combined JSON is only the explicit portable format. Restore requires explicit renderer confirmation.

Electron uses the `com.expletive-deleted.desktop` Windows AppUserModelID, private `expletive-deleted:*` IPC channels, and the narrow typed `window.expletiveDeleted` preload API.

- The Dictionary displays the durable user path and policy metadata; processing loads the same complete policy at job start.
