# Expletive Deleted Desktop

Electron hosts the React renderer in this directory. This is an installed desktop application, not a browser-hosted application.

Native IPC handlers must use `trustedIpcHandlers` from `electron/ipc-security.ts`. The sandboxed preload is bundled; `renderer-policy.ts` owns trusted document matching and the separate production/development CSPs. After building, run `npm run smoke:security` for real Electron and Vite/HMR boundary tests. Packaged smoke runs the same production checks. See [HP-01 implementation](../docs/HP-01_IMPLEMENTATION_2026-09-17.md).

The shared `scripts/security-checks.mjs` redirect check starts from its inert HTTP fixture. Reloading React immediately before that check can let HashRouter initialization interrupt the pending navigation before the server receives it. The check requires an actual redirect request, prevention of the exact target by Electron, and zero requests to that target; a generic `ERR_FAILED` is not accepted as security evidence.

`electron/native-files.ts` owns the generic backend allowlist and native playback/dictionary actions. After building, `npm run smoke:native-files` tests those actions through actual main/preload handlers and guarded Python operations. See [HP-02 implementation](../docs/HP-02_IMPLEMENTATION_2026-09-17.md).

From `frontend/`:

```powershell
npm install
npm run dev
```

`npm run dev` launches Electron. Vite is used only as Electron's renderer build and hot-reload tool.

The Python child starts through `scripts.desktop_bridge`, a thin entrypoint for `backend.desktop.protocol`. Request routing, dictionary responses, and setup workers have separate backend modules; see the [Python module guide](../backend/README.md).

Production validation:

```powershell
..\scripts\build_local_release.ps1
```

The local release command runs the same validation and audited installer stages as the GitHub release workflow. It accepts Node.js 22.12.0 or later and obtains the checksum-verified Python 3.13.15 runtime automatically when needed. The installer contains the application and private Python payload; FFmpeg/FFprobe, yt-dlp, Deno, Python packages, and the selected Whisper model are verified or obtained through explicit onboarding setup. Whisper models remain user-selected and are never bundled.

The Windows package wrapper cleans incomplete generated staging directories and retries Electron Builder's transient `EPERM` rename failure up to three times. If cleanup remains locked, close any packaged Expletive Deleted process and Explorer window open to `frontend/release`, then run the command again.

The package audit requires private Python and rejects processing packages, FFmpeg/FFprobe executables and libraries, yt-dlp, Deno, Whisper model payloads, and accidental development binaries. Electron's single root `ffmpeg.dll` remains framework-owned Chromium codec support and must not satisfy the application's FFmpeg readiness check.

`npm run package:win` requires `BUNDLED_RUNTIME_DIR` even outside CI and refuses to create an installer without private Python. `package:dir` still supports the development-only package used by CI. For a separate build directory, set `PACKAGE_AUDIT_ROOT` to its `win-unpacked` directory and `PACKAGED_EXECUTABLE` to its executable before running the audit and packaged smoke commands. The setup-first smoke checks fresh Unicode application-data and media paths, a restricted system PATH, and conflicting system Python configuration without obtaining processing components.

## Renderer architecture

See the [renderer developer guide](src/README.md) for module ownership, state rules, and extension guidance, and the [frontend review](../docs/FRONTEND_REVIEW_2026-09-16.md) for completed improvements and remaining findings.

- `src/App.tsx` composes the shell, global status, and routes.
- `src/features/` owns Queue, Dictionary, Settings, Onboarding, and capability state.
- Queue calculations and snapshot loading live in `queue-model.ts` and `queue-data.ts`; page, table, row, archive, and dialogs have separate owners. Settings sections, dictionary table rendering, and setup progress are also separate components.
- `src/features/onboarding/` keeps each walkthrough section in its own component: Welcome, Components, Initial Settings, Add Media, Process Media, Finish, and backend-startup recovery. `OnboardingPage.tsx` owns only composition, saved-step navigation, and the temporary settings draft.
- `src/components/ui/` contains reusable controls and presentation primitives.
- `src/services/desktop-client.ts` is the typed boundary around Electron IPC.
- ESLint prevents renderer Node/Electron imports and direct preload access outside the typed client. This development guard does not replace runtime IPC validation.
- React Router handles renderer navigation, TanStack Query owns backend state, and React Hook Form owns the persisted/draft settings lifecycle.

## Queue behavior

- Closing Electron sends EOF to the bridge, waits for cancellation cleanup, and uses a 15-second forced-exit fallback. Windows descendants belong to the bridge's kill-on-close Job Object. `npm run smoke:shutdown` exercises actual window closure with cooperative and unresponsive synthetic encoders; CI and local release validation run this check too.
- Settings updates and job submissions share a backend lifecycle lock. Active YouTube downloads block saving settings until their local-job handoff completes.

- Each local file exposes **Transcribe** or **Retranscribe** and guarded **Archive** actions. Archive requires a verified transcript or output and no queued or active job for that source; unrelated jobs do not block it. Censor submission is available in bulk from the Transcribed filter.
- Ready-file checkboxes submit transcript jobs; Transcribed-file checkboxes submit an exact ordered censor selection through the typed `jobs.submit_many` bridge operation.
- The table shows each locally probed media length, can filter Ready, Queued, Active, Transcribed, and Finished rows, and can sort by queue position, file name, or status.
- Waiting jobs show their position and can be removed independently; the running job can be cancelled from its row or the top-level cancel action.
- The optional persisted setting `processing.auto_censor_after_transcription` promotes each newly verified transcript to the censored-copy queue. `processing.auto_transcode_youtube_downloads` starts the same chain after a completed YouTube download.
- The renderer never decides that a transcript is safe for transcoding. That mandatory persisted-artifact gate belongs to the Python backend.
- Source hashing appears as **Verifying** with **Checking source contents** progress. Startup and polling never hash media; transcript/output rows describe recorded state. **Needs review** rows preserve unidentified artifacts, disable bulk selection, playback, and archival, and offer an explicit **Retranscribe** action. The backend enforces identity even when submissions bypass these controls.

## Desktop ownership

`electron/single-instance.ts` claims Electron ownership before startup. A second launch restores/focuses the first window, including requests received before its first paint. The stable profile is `<application-data>/desktop`; `CENSOR_APP_DATA_DIR` isolates both the profile and backend data for tests.

After building, run `npm run smoke:state` to exercise two real launches, one window/bridge owner, startup focus, minimized-window restoration, and concurrent CLI/desktop edits. CI, local validation, and release gates run it sequentially with other native smoke tests.

## Dictionary behavior

- The resource text files are built-in defaults and are never edited by the renderer.
- The live policy uses backend-managed `censored.json`, `exclusions.json`, and `discovered.json` stores beneath `%LOCALAPPDATA%\ExpletiveDeleted\dictionary`.
- Import, export, validation, and restore-defaults behavior remain backend-owned. Combined JSON is only the explicit portable format. Restore requires explicit renderer confirmation.

Electron uses the `com.expletive-deleted.desktop` Windows AppUserModelID, private `expletive-deleted:*` IPC channels, and the narrow typed `window.expletiveDeleted` preload API.

- The Dictionary displays the durable user path and policy metadata; processing loads the same complete policy at job start.

## Settings and component conflicts

`settings.get` returns `{ settings, revision }`. Normal Settings submits a complete draft with its baseline; onboarding submits intended field changes. Both use the shared backend transaction and `SettingsConflictDialog`, retaining drafts while a choice is pending. Setup uses `awaiting_resolution` and `dependencies.resolve_conflict`; retries verify retained files and never approve another installation. All wire operations live in `src/services/desktop-client.ts`.

The wizard starts from `persistedSnapshot`, separately from the normal Settings form. Its baseline changes only after a successful `saveWizardDraft`; `wizardChanges` limits patches to its controls plus explicit saved-step/Finish intent. Background cache updates cannot reset its step or draft. A picker result arriving during a save remains editable on the current step. Conflict retries compare against the returned revision with strict checking; a newer revision requires fresh choices. The dialog stays mounted across revisions so Escape/Cancel restores focus to the original trigger.

CI explicitly runs `useSettingsController.test.tsx`, `SettingsConflictDialog.test.tsx`, and `OnboardingPage.test.tsx`, alongside the full frontend suite and backend settings/component transaction gates. Native state smoke additionally checks wizard conflict cancellation, keyboard radio choices and focus trapping/restoration, another write during resolution, and saved-step resume after reload.

`npm run smoke:state` runs real Electron/backend settings races, wizard preservation, repeated resolution without installation replay, and CLI ownership checks. Its offline fixture replaces component verification/downloads only; no test installs processing components. Screenshots cover both themes at 1060?720 and 1440?940.

## Setup connection and recovery

`installation-connection.ts` owns serial status reads, monotonic deadlines, 1/2/4/8-second backoff and stale-response rejection. `useInstallStatus` binds observer lifetime to the current operation. Connection state remains separate from `InstallStatus`, including `awaiting_resolution`.

The main-process `BridgeTransport` removes timed-out requests and ignores late replies. Status reads are bounded to two seconds. The preload exposes a sanitized backend-state subscription with an unsubscribe function and generation ID. The typed client unwraps structured responses in the renderer because Electron strips custom properties from errors crossing `contextBridge`. No mutation is automatically replayed. Approved-token lookup recovers a lost start acknowledgement, and Python dispatch reserves the input/control path for quick setup state reads, cancellation flags and worker scheduling.

After building, run `npm run smoke:recovery`. Its offline fixture drops acknowledgements and status replies, occupies normal workers, and exits the backend. It tests a real 30-second silence window, explicit restart, retained synthetic downloads, fresh approval, keyboard access and live-region feedback. Screenshots cover light/dark at 1060x720 and 1440x940. CI, release and both local validation scripts enforce this gate. The test harness records relaunch and lets Playwright launch the replacement process; production uses Electron relaunch with bounded shutdown.
