# HP-08 implementation - 2026-09-24

Setup now shows a visible reconnection phase after losing contact, with elapsed time and a monotonic 30-second deadline. It resumes from actual backend status. After the deadline the installation outcome remains explicitly unknown, with status-only Retry connection and explicit Restart app actions. A known backend exit shows recovery immediately. Neither recovery action replays approval or cancellation.

## Implementation

- `frontend/electron/bridge-transport.ts` owns request correlation, UTF-8 line decoding, envelope validation, deadlines and classified transport errors. Setup status, active-plan lookup, start acknowledgement and cancellation acknowledgement are bounded to two seconds. Timed-out entries are removed; late responses cannot settle another request. Unrelated long media operations retain their existing lifetime.
- The preload exposes a narrow sanitized backend-state subscription with a generation ID and unsubscribe function. Only the trusted application window receives events. The typed client unwraps structured errors in the renderer: native testing confirmed that Electron strips custom error properties when an Error crosses `contextBridge`.
- Python reserves its input/control path for quick status reads, approved-token lookup, cancellation flags and approved-worker scheduling. These operations never verify components or wait for installation. Dispatching them serially outside the ordinary worker pool avoids queued duplicate status work under saturation. Strict JSON serialization failures return correlated protocol errors.
- `dependencies.active` reconciles a lost start acknowledgement by the already approved token, including terminal outcomes. Repeated approval returns the same operation; conflicting active component plans report `setup_busy`.
- `installation-connection.ts` and `useInstallStatus.ts` own serial polling, 1.2-second spacing after successful reads, 1/2/4/8-second retry delays, remaining-window caps, operation/generation checks and cleanup. Responses after unmount, operation change, timeout or backend generation change cannot update progress.
- Cancellation acknowledgements trigger fresh status reads. Lost acknowledgements retain uncertainty. Confirmed terminal outcomes refresh settings/readiness once. HP-04's shared `awaiting_resolution` state continues to use the existing settings conflict dialog and revalidation mechanism.
- Recovery has keyboard focus handling and a polite live region. Background progress remains reachable from the header at 1060x720 and 1440x940, in both themes. Settings conflicts and setup recovery do not open competing modals.

## Validation

Validated locally on Windows with repository Python 3.14.0 and Node.js 24.12.0:

- Full backend discovery: **344 tests passed**. After the final malformed-request regression, focused setup-control and desktop-protocol suites: **27 passed**.
- Full frontend suite: **191 tests passed** in 17 files. Follow-up App/transport checks: **69 passed**; final transport/connection/hook checks: **23 passed**, including the additional regression protecting long media imports from setup deadlines.
- Typecheck, lint and production build passed.
- Native recovery smoke: all **seven required cases passed**, including a real **30.1-second** visible silence window, transient recovery, lost start/cancel acknowledgements, saturated workers, status-only retry, backend exit and explicit restart with preserved synthetic downloads and fresh approval.
- Native state smoke: all seven settings/ownership/conflict cases passed. One earlier run encountered Windows `WinError 5` during atomic settings replacement; the save error was surfaced, and a fresh run passed without changing persistence behavior.
- Standard Electron smoke passed. Security smoke passed in production and Vite development, including all ten IPC channels, hostile documents/windows and rejected fixture operations. The same security checks run in packaged validation and verify the exact narrow preload surface.
- Graceful and forced shutdown smoke passed. Recovery screenshots were inspected in both themes at both supported sizes; keyboard focus, live-region metadata, background reopening and content fit are also asserted by the native harness.

The recovery fixture replaces downloads and verification with local synthetic files, while exercising the real main process, preload, renderer, Python dispatch and settings store. To let Playwright attach to the replacement process, its test harness records the explicit relaunch request and launches the replacement itself. Production uses Electron relaunch and the existing bounded shutdown path. No processing components were downloaded or installed, and no packaged installer or remote workflow was run for this change.

## Required gates

Backend CI explicitly runs setup-control, installation-conflict and settings-transaction tests. Existing frontend test/type/lint gates discover the new modules. `npm run smoke:recovery` is required by Electron Smoke, the unpublished-release validation path, `scripts/run_all_tests.ps1` and `scripts/build_local_release.ps1`. Electron Smoke now allows 45 minutes and retains failure screenshots and case summaries through its existing artifact upload. Release triggers, permissions and publishing behavior are unchanged.

Inline notes explain observer lifetime, deadline ownership, stale-response rejection, protocol decoding and conflict-payload validation. The user authorized committing HP-08 after this review. No push, tag or remote issue update was made.
