# HP-01: Trusted desktop renderer

All eight IPC handlers now use `trustedIpcHandlers`. Only the current application's top-level document may dispatch native/Python work. Foreign windows/documents, child or detached frames, and results outliving a reload are rejected. Handlers recheck the caller before native side effects following an await.

`renderer-policy.ts` owns document matching and CSP. Installed builds ignore `ELECTRON_RENDERER_URL`; development accepts only `http://127.0.0.1:5173`. Production trusts the exact built file with hash routes and launch queries. Unexpected navigation, redirects, popups, subframes, and permissions are denied. Deliberate HTTPS links continue through the default-browser handler.

The preload is bundled and sandboxed. Production CSP prohibits inline scripts, eval, network connections, frames, plugins, form submission, and base-tag overrides. Inline styles remain for existing React styling. Development separately permits React refresh and the exact Vite WebSocket endpoint. Generated package/runtime folders are excluded from Vite watching.

## Tests and CI

`ipc-security.test.ts` covers URLs, Unicode paths, sender/frame ownership, request lifetime, navigation, and permissions. `smoke-security.mjs` tests real production/Vite windows, every IPC channel, foreign documents loaded by the harness, an extra window showing the trusted document, actual CSP enforcement, sandbox preferences, native file-path extraction, and a WebSocket-triggered Vite reload. Native side effects are intercepted.

Packaged smoke reuses these checks and deliberately retains a hostile renderer environment URL. Frontend Tests runs the unit tests; Electron Smoke, Release, and local release validation run native security checks. ESLint directs new IPC registrations through the guard.

Validation: 122 frontend tests, TypeScript/build, ESLint, native production/development security, normal Electron smoke, and graceful/forced shutdown passed. Packaged evidence is included in the integrated handoff.

HP-02's file-launch/export authorization remains open. A trusted renderer does not imply that every requested file operation is safe. See the [decision register](HIGH_PRIORITY_ISSUES_AND_DECISIONS_2026-09-17.md).
