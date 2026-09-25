# High-priority repair, validation, and CI plan

Date: 2026-09-17  
Status: **planning only; no application, test, or CI changes implemented by this document.**  
Source baseline inspected: `845ced9` on `refactor/python-backend-modules`.

## Scope and decisions

This is the second document following [High-priority issues and product decisions](HIGH_PRIORITY_ISSUES_AND_DECISIONS_2026-09-17.md). Those product decisions control this plan. Module names, APIs, test names, and CI steps described as new below are proposed implementation specifications, not existing capabilities or completed verification.

Eight issues were in the original repair scope. **September 25 update:** the owner separately authorized source identity implementation, recorded in [source identity behavior and benchmark](SOURCE_IDENTITY_DISCUSSION_2026-09-25.md). Legacy migration remains deferred. Existing artifacts are not renamed, adopted, or regenerated automatically, and startup/polling never hash the user's collection.

Implementation must preserve original media, complete settings drafts, existing dictionary entries, explicit setup consent, and the Python-only installer distribution model. No model, FFmpeg, yt-dlp, Deno, or processing package is to be added to the installer. No product-site publishing, release, tag, commit, or push is authorized by writing this plan.

## Delivery order and ownership

Each implementation change must include its regression tests and applicable CI wiring in the same reviewable change. Do not defer test enforcement until the last change.

| Order | Scope | Main owners | Completion condition |
| --- | --- | --- | --- |
| 1 | HP-01: trusted renderer boundary | Electron main/preload, renderer build | Foreign callers cannot invoke native or Python operations; normal development and packaged routing work |
| 2 | HP-07 and shared filesystem/locking foundations | New `backend/filesystem/`, settings directory handling | Native Windows containment and cross-process locking tests pass |
| 3 | HP-06: common verified publication | Jobs, batch, downloads, transcript writes | Failure/cancel/collision preserves originals and existing output across entrypoints |
| 4 | HP-02: authorized native file operations | Electron native handlers, backend output service, typed client | No renderer-supplied arbitrary launch/export path reaches a native operation |
| 5 | HP-03: dictionary transactions and one desktop instance | Policy store, Electron lifecycle | Concurrent accepted edits survive; one desktop process owns the user's app window |
| 6 | HP-04 and HP-09: shared settings conflicts | Settings store/service, setup controller, settings/onboarding UI | Both directions of stale-snapshot overwrite are prevented |
| 7 | HP-08: connection recovery | Main-process transport, Python control dispatch, capability UI | Visible bounded reconnect; no installation replay; accurate reconciliation |
| 8 | Integrated Windows qualification | CI, package smoke, local release validation | All issue gates below pass on one final revision |

HP-04 and HP-09 share one settings mechanism; they must not introduce two competing merge implementations. HP-02 consumes HP-07 containment and HP-06 publication. The one-instance guard should land before new native multi-launch tests become mandatory.

## Shared implementation contracts

### Filesystem ownership and errors

Create `backend/filesystem/paths.py`, `locking.py`, `publication.py`, and a narrowly scoped Windows adapter `windows.py`. Use the standard library and explicit Win32 bindings where necessary; keep them independent of Whisper and other processing packages.

- `RootBinding`: configured root, resolved root, and available volume/directory identity.
- `DestinationLease`: validated parent chain and target identity, with native handles retained for the operation's critical section. Never expose this object to the renderer.
- `PublicationRequest`: source, root binding, final relative name, verification callback, cancellation token, and explicit replacement authorization.
- Stable error codes: `outside_root`, `root_changed`, `destination_changed`, `destination_exists`, `source_destination_alias`, `verification_failed`, and `store_busy`. Messages must distinguish failure from a safely retained existing result.
- Reject source/destination identity equality, including hard-link aliases; a matching path string is not the only way to overwrite a source.
- Cleanup may remove only a staging file demonstrably owned by the operation. Never infer ownership from a `.partial` suffix alone or delete an unexpected final file.

Use a registry of per-canonical-path thread locks plus an OS-backed lock file for cooperating processes. On Windows, lock a fixed byte with nonblocking `msvcrt.locking`, with a monotonic five-second acquisition deadline; unlock in `finally`, and do not delete the lock file on release. Keep reentrancy in the wrapper rather than reacquiring the OS lock recursively. A process crash must release the OS lock. Use `fcntl` behind the same interface on supported POSIX systems. This is a proposed use of the [Python locking API](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking), not a new runtime dependency.

Document and test lock ordering: service lifecycle lock, settings transaction, root bindings, then sorted destination leases. Do not acquire settings while holding a policy transaction. Release all persistence locks before model loading, installation, transcription, network work, or UI conflict resolution. Snapshot policy under its lock, then release it before processing.

### Structured errors and private protocol changes

Extend Python response errors, `frontend/electron/ipc-response.ts`, `frontend/src/electron.d.ts`, and `frontend/src/types/domain.ts` together. Preserve validated `code` and structured `details` fields; do not serialize entire exception objects or make the renderer parse message text. Add `DesktopError` at the typed client boundary.

All changed wire names remain in `frontend/src/services/desktop-client.ts`. Replace obsolete raw calls in smoke fixtures and tests at the same time. Keep root Python entrypoints thin. The private desktop protocol can change in one coordinated application revision; tests must reject old unsafe payload shapes rather than preserve them as an undocumented bypass.

## HP-01: Trusted window, navigation, and IPC callers

### Implementation

1. Extract `frontend/electron/ipc-security.ts` and a small registration helper used by **every** native handler, including generic invoke and any new subscriptions/recovery handlers. Validate that the sender is the current trusted window, the sender frame exists and is that window's top-level frame, and its current document URL is trusted. Revalidate ownership after awaiting a native dialog and before acting on its result.
2. Production trust is the exact normalized built renderer document, allowing application hash routes and the app's existing harmless launch query parameters. Compare parsed URLs and decoded canonical file paths, not string prefixes or a `file:` origin alone. Reject other files, `about:blank`, `data:`, unexpected hosts, and subframes.
3. Honor `ELECTRON_RENDERER_URL` only when `app.isPackaged` is false. Validate the development endpoint as the configured loopback Vite host/port/document. Do not let arbitrary environment-provided remote sites become trusted. Keep hash routing working in both modes.
4. Install `will-navigate`, `will-frame-navigate`, redirect, and `setWindowOpenHandler` policies before loading the document. Deny unexpected documents/windows. Route deliberate supported HTTPS links through the validated external-link handler and the default browser; do not automatically launch every blocked navigation attempt externally.
5. Enable `sandbox: true`; preserve `contextIsolation: true`, `nodeIntegration: false`, and web security. Bundle the preload's local helper imports so sandboxed preload does not require arbitrary Node modules at runtime.
6. Add a production CSP through the renderer build: default/script/font/image sources limited to bundled assets, `connect-src 'none'`, and `object-src`, `frame-src`, `base-uri`, and `form-action` denied. Permit inline **styles only** where existing React style attributes require them; never enable inline script or `unsafe-eval` in production. Development gets a separate generated policy allowing only its exact HMR connections and React development requirements.
7. Deny unnecessary session permission requests. Do not add a general-purpose renderer filesystem, shell, URL-loading, or IPC API.

These controls follow [Electron's security guidance](https://www.electronjs.org/docs/latest/tutorial/security). Exact event signatures must match the installed Electron typings, rather than copied examples from another major version.

### Tests and exit criteria

- New `frontend/electron/ipc-security.test.ts`: table-driven legitimate URL/hash cases, Unicode/encoded paths, prefix lookalikes, foreign windows, null/destroyed frames, same-window child frames, forged senders, and packaged development-URL overrides. Assert rejection occurs before backend dispatch or OS calls for every registered channel.
- New `frontend/scripts/smoke-security.mjs`: load the real built main/preload; attempt loopback foreign navigation, redirects, `window.open`, and iframe access. Assert no new privileged window, no successful foreign IPC, and normal Queue/Settings/Dictionary routing.
- A test-created foreign window with the real preload must be rejected even if navigation prevention is bypassed by the test harness. Do not count navigation blocking alone as sender-validation coverage.
- Verify sandbox preferences, CSP absence of executable inline/eval permissions, development HMR, dropped-file path extraction, and normal pickers. Intercept external launching; do not launch executables or browse outside the fixture.
- Run packaged checks with a hostile `ELECTRON_RENDERER_URL` deliberately retained in the test environment and verify it is ignored. Existing packaged smoke removes that variable, so its current coverage is insufficient.

CI owner: Electron security unit tests run in Frontend Tests; native cases run in Electron Smoke and release/local validation. Packaged cases run against the built artifact before release publication.

## HP-02: Safe playback and picker-bound exports

### Implementation

1. Replace renderer `openFile(path)` with `openOutput(source)` in `QueueRow`, `useQueue`, desktop client, declarations, and preload. The backend derives the output from current settings and library/job information; it never treats the argument as a destination to launch.
2. Add `backend/service/outputs.py` with an internal `prepare_open` operation. Resolve within the configured output binding, reject unsupported extensions, executables/shortcuts, directories, streams, and source aliases, then check that the file is nonempty and passes the existing bounded media verification. Missing FFprobe gives an actionable verification error; it does not trigger a download.
3. Return an internal, short-lived open lease to Electron main with the canonical path. Keep parent/file identity protected through the OS handoff, recheck immediately before `shell.openPath`, and release in `finally` or on bridge/window loss. Expire abandoned leases after 30 seconds. Generic renderer invoke cannot call internal prepare/release methods or supply a lease path.
4. Replace the two-step renderer `selectDictionaryExport()` / `exportDictionary(destination)` flow with one native `exportDictionary()` action. Main owns the Save dialog and selected path throughout; no arbitrary destination comes back from the renderer for a later write.
5. Validate the `.json` destination and its parent, capture the selected existing-file identity if any, and obtain explicit overwrite confirmation bound to that selection. A changed destination requires a fresh decision. Delegate the write through the common publication helper with those constraints; cancel means no write.
6. Remove `dictionary.export` from the generic renderer forwarding allowlist; retain a main-only route to the private Python operation. Apply the same main-owned picker pattern to dictionary import so a second native channel does not retain an arbitrary-path bypass. CLI export remains a separate explicit user-command workflow.
7. Return structured completion/cancel/failure to `useDictionary`; catch picker and export errors together. Retain typed error reporting in Settings/support/setup external-link actions touched by this boundary change.

### Tests and exit criteria

- New `tests/test_output_access.py`: valid audio/video, missing/empty/unreadable files, missing verifier, outside-root paths, file/junction aliases, changed targets, source aliases, and lease expiration/cleanup. Verification uses controlled probe results, not a model download.
- Extend native security smoke with intercepted `shell.openPath`: only a validated output path reaches it. Inject `.exe`, `.cmd`, `.bat`, `.lnk`, `.url`, alternate streams, and external media paths; assert zero native launches.
- New `frontend/electron/native-files.test.ts`: export cancellation, approved JSON creation, approved replacement, unsupported extension, sender destruction during a picker, target replacement after confirmation, repeated calls, and generic-method bypass rejection.
- Extend `tests/test_desktop_bridge.py` and dictionary UI tests for the new contracts and actionable picker failures. Assert existing sentinel bytes survive every rejected export.
- Run the native export test through the real main handler with dialogs mocked at the Electron API boundary; recording an invocation of a renderer mock does not establish native authorization.

CI owner: Backend CI, Frontend Tests, and native security smoke. No relocated-file UI is included.

## HP-03: Dictionary transactions and one desktop instance

Implemented on 2026-09-23; see [acceptance evidence and platform limits](HP-03_IMPLEMENTATION_2026-09-23.md).

### Implementation

1. Acquire `app.requestSingleInstanceLock()` before spawning Python or constructing a window. Use stable per-user application identity. On `second-instance`, restore/focus the existing window; if it is not ready yet, retain a focus request. The losing process exits without starting a bridge. See [Electron's single-instance API](https://www.electronjs.org/docs/latest/api/app#apprequestsingleinstancelockadditionaldata).
2. Put complete policy transactions inside `backend/policy/store.py`, using the shared OS/thread lock keyed by the resolved dictionary directory. All initialization, add/remove/classification, discovered-word updates, import, restore, export snapshots, and reads must use the same ownership rule, including CLI callers.
3. Retain the existing split JSON formats and paths. Add `backend/policy/transactions.py` with a recoverable redo journal rather than migrating the user's dictionary to a new database in this repair.
4. Under the lock: read the current complete policy, calculate and validate the update, write a flushed atomic journal containing the transaction ID and intended payloads for fixed permitted store names, replace affected store files, then remove the journal. Acknowledge success only after publication completes. Never accept arbitrary journal destination paths.
5. Readers acquire the lock and recover a valid pending journal before returning a snapshot. A crash after journal publication is recovered by completing its intended transaction before any reader sees partial state. A corrupt journal or unrecoverable I/O failure gives a repair error; never silently seed defaults over existing data. An interrupted request may have committed, so retry must reconcile current policy.
6. Preserve schema versions, timestamps, imported/default provenance, and untouched entries. First-run creation uses the same transaction path. A targeted exclusions read may retain its existing ability to read valid exclusions without validating unrelated censored entries, once pending transaction recovery has completed under the lock. Recovery data stays local and must not enter routine logs or CI artifacts.

### Tests and exit criteria

- New `tests/test_policy_transactions.py` plus existing policy/durable-store tests: two threads, two distinct store objects, and two independent Python processes concurrently add/remove/classify. Use barriers/events, not sleeps, and assert every acknowledged edit survives.
- Race import/restore with edits; exercise discovered-word writers while a dictionary editor is active. Assert a word cannot appear in contradictory censor/exclusion states in any returned snapshot.
- Inject failure or terminate a synthetic process before journal publication, after each store replacement, and before journal cleanup. Reopen and verify an internally consistent recovered policy with preserved provenance. Exercise invalid journal, lock timeout, and lock-owner death.
- New `frontend/scripts/smoke-state.mjs`: launch two real Electron processes under one isolated user profile, verify one window/bridge owner and second-launch focus. Run separate test cases sequentially so the new guard does not cause false smoke failures.
- Keep a test for CLI dictionary edits while the desktop owns the window; single-instance enforcement is not a replacement for shared storage locking.

CI owner: Backend CI for real subprocess transactions, Frontend Tests for lifecycle helpers, native state smoke for actual second-launch behavior.

## HP-04 and HP-09: One settings transaction and conflict mechanism

### Shared backend contract

Create `backend/settings/transactions.py`. Extend the store to read and compare persisted state while holding its OS/thread lock; do not compare only `BackendService.settings`. Keep the human-readable INI schema unchanged. Calculate an opaque revision from canonical validated settings values, not timestamps alone, and return:

```text
SettingsSnapshot = { settings: Settings, revision: string }
FieldChange = { field: allowed leaf path, expected: value, value: proposed value }
SettingsConflict = { field, expected, current, proposed }
```

- Desktop `settings.get` returns `SettingsSnapshot`.
- Desktop `settings.update` accepts the complete draft plus its base snapshot/revision. Backend derives the changed leaf fields from base versus draft, merges those onto current persisted state, and validates the entire merged result.
- New `settings.patch` accepts a revision and explicit `FieldChange[]` for onboarding changes/progress. Allowlist leaf fields, validate value types, and reject duplicate/unknown paths and schema-version edits.
- For each changed field: if current equals expected, apply the proposal; if current already equals proposed, treat it as satisfied; otherwise report a conflict. Preserve untouched current fields. On any conflict, save **nothing** and return all conflicts plus the latest snapshot.
- Resolving a conflict uses a fresh baseline and the user's choices. Compare again; another concurrent change must produce another conflict rather than an unconditional force-save.
- Serialize with the lifecycle lock, retain the active-local-job/download settings guard, validate directory effects before committing settings, and keep managers/in-memory settings consistent with a successful save. Manager construction or persistence failure must not leave a success response with unusable managers.
- Route supported CLI settings writers through the same store transaction. Prevent CLI settings mutation while a live desktop owns that profile, with an actionable `settings_busy` result; dictionary CLI transactions remain allowed. This is a proposed technical protection against a CLI process bypassing the desktop's active-job gate.
- Tests must cover environment/legacy overrides in `settings/resolver.py`: a snapshot revision describes the effective settings being edited, and overridden fields cannot be silently persisted as if they were ordinary saved values.

Update `backend/desktop/bridge.py`, protocol error serialization, typed client/types, `useSettingsController`, existing CLI adapters, and all raw settings calls in smoke fixtures together. The normal Settings page still submits its **complete validated draft**; change detection is backend merge logic, not partial accidental autosaving.

### HP-04 setup-specific changes

1. Capture expected runtime values, selected model, and destinations when creating a plan or beginning a locate-existing inspection. Preserve immutable verification destinations with the approved plan; do not resolve a new cache directory after approval.
2. After verification, call an internal `apply_runtime_changes` restricted to fields actually supplied by successful components. Never send an old complete settings object. Treat FFmpeg/FFprobe paths as one verified pair.
3. If concurrent edits conflict, retain installed files and expose `awaiting_resolution` with structured conflicts. Do not claim the system is ready or rerun the installer to fix a settings conflict. An active-job guard can similarly leave verified components awaiting application.
4. Add `dependencies.resolve_conflict` accepting the install/inspection ID, a fresh expected revision, and per-field keep-current/use-verified choices. Revalidate the verified component before applying it. Retrying conflict application is a settings action, not a new installation approval.
5. Update capability and progress views to show that components are verified but settings need attention. Completion and readiness remain distinct; a user may keep a manual path that is still unready.

**Tests:** new `tests/test_settings_transactions.py` and `tests/test_installation_conflicts.py`; extend `test_settings.py`, `test_backend_service.py`, `test_model_cache_consistency.py`, and `test_desktop_bridge.py`. Pause setup/locate after baseline capture, save newer onboarding/preferences/runtime fields, then finish. Assert unrelated edits survive, same-field conflicts publish nothing, FFmpeg pairs remain consistent, duplicate component completions do not lose paths, and conflict resolution never calls installation twice. Include process-level CLI contention, validation failure, disk error, and active-download cases.

### HP-09 onboarding-specific changes

1. Store the wizard's baseline separately from its draft. Record intended edits and onboarding progress; compare against the wizard baseline, not the latest background query result.
2. On Save & Continue/Finish, submit those changes through `settings.patch`. Do not advance until the whole patch succeeds. Replace the baseline with the returned snapshot after success, preserving newer unrelated settings in subsequent steps.
3. Add a shared `SettingsConflictDialog.tsx` in the settings feature. Show current and proposed values for conflicting fields, retain all draft edits, and require a choice before resubmission. Cancel closes the dialog without discarding the draft or advancing the wizard.
4. Normal Settings save/discard uses the same conflict presentation. Disable duplicate saves while pending; do not allow a late success to erase edits made after its submitted draft. Queue polling remains independent of settings reloads.
5. Onboarding Back, resumed onboarding, and replayed onboarding must retain their established progress semantics. A component completion must not reset the current step.

**Tests:** new `useSettingsController.test.tsx`, `SettingsConflictDialog.test.tsx`, and `features/onboarding/OnboardingPage.test.tsx`, plus existing `App.test.tsx` integration cases. Cover unrelated background updates, exact same-field conflicts, keep-current/use-draft, another change during resolution, failed saves, cancel, discard, double clicks, saved-step resume, and untouched form fields. Native state smoke performs a real backend settings update between wizard steps and asserts the final persisted values.

The conflict dialog must trap focus, restore focus, support keyboard choices, and preserve readable light/dark rendering at 1060×720 and 1440×940. Its new copy should be reviewed as part of implementation; this plan does not supply final UI wording.

CI owner: Backend CI, Frontend Tests, Frontend Quality for the coordinated contract, and native state smoke. These two issue IDs close together only when both write directions pass.

## HP-05: Deferred source identity and legacy migration

The historic heading is retained for existing links. The owner subsequently requested implementation on September 25. Full-file SHA-256 now binds new transcripts and outputs to sources; publication collision protection alone does not establish this relationship. Legacy names and artifacts are preserved, with unidentified entries requiring review.

The [September 25 implementation record and initial benchmark](SOURCE_IDENTITY_DISCUSSION_2026-09-25.md) describe source digests in transcript JSON, provenance companions for finished copies, source-extension naming, and verification at use rather than startup or library polling. The standalone [PowerShell benchmark](../scripts/measure_file_sha256.ps1) remains available. Initial measurements substantially reduced the owner's timing concern, but do not qualify external-drive performance.

The implementation uses cancellable chunked SHA-256, existing Windows read leases, explicit failure on mismatches, unique compatible fingerprinted-transcript lookup for relocated files, and preserved transcript history. Remaining qualification covers representative originals on local/external drives and disk impact. A one-off preview/confirm legacy mapping tool remains future work. Benchmark authorization is limited to explicitly selected files, not a collection-wide scan.

Regression coverage now includes same-stem/different-extension naming, same-size source changes, renamed-file reuse and ambiguity, cancellation, original-byte preservation, transcript history, provenance interruption/retry, and hash-free polling. Existing CI discovers the tests and native Electron smoke covers legacy review and verified playback. No expected-failure tests or automatic legacy normalization were added. Migration recovery tests remain deferred with the migration tool.

## HP-06: Shared verified publication

### Implementation

1. Move the existing desktop staging/publication behavior into `backend/filesystem/publication.py`. Route desktop censorship/copy, `backend/jobs/batch.py`, `backend/jobs/downloads.py`, service import/restore/archive, and transcript persistence through the relevant guarded operations. Preserve each operation's explicit overwrite policy.
2. Allocate a unique staging file exclusively in the validated destination parent on the same volume. Preserve the final media suffix for container detection. Capture source and authorized replacement identities before work; reject source/destination aliases.
3. Verification remains operation-specific: censored/downloaded media must be nonempty with required readable streams; imports compare copied byte count and source identity before/after; transcripts validate their existing schema/model/channel contract before publication. This repair does not add source fingerprints to transcripts or claim full decode/recognition accuracy.
4. Flush and close staging output, check cancellation, acquire the destination lease, and revalidate the parent/root and target identity before publication. New files use an atomic no-replace operation: preserve the current Windows collision-refusing rename behavior; POSIX uses same-volume no-replace/link semantics with an explicit unsupported-filesystem error instead of overwriting fallback.
5. Replacement requires the existing explicit UI/CLI overwrite authorization and must be bound to the intended destination. Serialize app writers, reject a target that changed since authorization, and use the platform publication adapter to preserve the old result if replacement fails. Never use an existence check followed by unconditional replacement for an unapproved new output.
6. Windows replacement/handle semantics are a mandatory native gate: prove replacement can be completed without an unprotected target-switch window while keeping failure recovery correct. If the filesystem cannot provide the required identity/lease guarantees, return a recoverable unsupported/conflict error and retain staging/old output; do not label a path-check-plus-`os.replace` sequence race-proof. Preserve any recovery file by identity and report it explicitly.
7. After successful publication, optional source archiving may run. A later archive failure must retain the verified output and source and report an archive-specific outcome; generic cleanup must not remove successfully published output. Cross-volume archive/restore uses verified copy plus guarded source removal only after destination success. Explicit purge still requires its own confirmation.
8. Unexpected collision stops the affected operation with `destination_exists`; do not invent a suffix or automatically retry with overwrite. Keep enough non-sensitive operation context for the user to make a new decision. CLI returns a clear failed/skipped result with a nonzero aggregate error status where appropriate.

### Tests and exit criteria

- New `tests/test_publication.py`, extend `test_job_manager.py`, `test_batch.py`, `test_downloads.py`, `test_output_verification.py`, `test_backend_service.py`, and `test_library.py`.
- Run the same contract cases through desktop censor, copy/import, batch, and mocked download preparation: partial writer failure, zero-byte output, invalid streams, cancellation before/during verification and immediately before publication, disk-full/write/flush/rename errors, and a destination created by a second process at the publication barrier.
- For replacement, assert old output bytes and original source bytes survive failure; verify unapproved replacement and changed authorized targets are rejected. For new-file races, exactly one writer succeeds and the loser's cleanup cannot delete the winner's file.
- Test same-file/hard-link aliases, cross-volume archive behavior, archive failure after successful publication, and `.partial` exclusions from the library. No test may process or delete real user media.
- Retain existing native graceful/forced shutdown scenarios. Extend the synthetic shutdown fixture to cover the shared publisher and assert no published incomplete output or surviving worker descendants.
- CI uses synthetic writers and mocked probes. A separate controlled real-FFmpeg qualification must validate actual container output and cancellation before release; no speech-model download is required for that qualification.

CI owner: Backend CI plus native shutdown smoke. The source-identity ambiguity in HP-05 remains open even when these publication cases pass.

## HP-07: Destination containment, including Windows junctions

### Implementation

1. Centralize resolution in `backend/filesystem/paths.py`; update `settings/directories.py`, `jobs/media.py` callers, service filesystem operations, censor transcript writes, and the common publisher. Cover creation, write, replace, move, archive restore, purge, and cleanup, not only output-name calculation.
2. Resolve the configured root first, permitting that root to be a symlink/junction. Bind its resolved target and filesystem identity. Store root bindings as local app metadata alongside settings, transactionally coordinated with folder-setting changes. Initialize existing configured roots once without moving media; a later changed binding requires explicit folder reselection/confirmation rather than silently trusting a new target.
3. Reject relative/drive-relative paths where an absolute root is required, traversal escapes, unsupported device paths, alternate data streams, reserved/ambiguous names, and source/destination aliases. Use component-aware containment and Windows case/volume semantics; string-prefix checks are insufficient.
4. For a not-yet-created parent, validate each existing ancestor, create missing directories through the guarded adapter, and bind each resulting directory. Follow links only if the actual resulting target remains inside the bound root. A link cycle, dangling link, unavailable drive, or changed root fails with an actionable error.
5. On Windows, use directory/file handles and final identity checks in `windows.py` to pin the relevant chain across creation/publication/removal. Use directory-opening flags and sharing restrictions that prevent rename/reparse retargeting during the critical section; release handles reliably on success, failure, cancellation, and process exit. The required handle/sharing behavior comes from the [CreateFileW contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
6. Rechecking `Path.resolve()` alone is not sufficient for the race gate. Native tests must attempt a target swap between validation and operation. If an operation/filesystem cannot maintain the binding, fail closed rather than follow an unverified path. On POSIX, use descriptor-relative/no-follow operations for supported cases behind the same contract.
7. Serialize archive/restore/purge with submission and settings lifecycle checks before source mutation. This includes the relevant part of bridge finding B05 as a dependency: containment does not help if a source is moved after being accepted for a job.

### Tests and exit criteria

- New `tests/test_filesystem_paths.py` and `tests/test_windows_destination_guards.py`: root junction to another directory, valid in-root links, child junction escaping root, dangling/cyclic links, sibling prefix lookalikes, Unicode/spaces/case variations, drive-relative/device/stream paths, missing parents, same-file/hard-link aliases, and root retargeting between sessions.
- At explicit barriers, retarget or replace a parent from a separate process before stage creation, final publication, source removal, and cleanup. Assert no outside sentinel is created, modified, moved, or deleted. Exercise the approved-root case positively so tests do not merely demonstrate blanket link rejection.
- Add archive-versus-submit, restore-versus-submit, and cleanup-versus-target-swap regressions. A denied operation must retain the source; a successfully queued job must not have its source moved by a competing operation.
- Windows junction cases are required CI tests, not silent skips. Create junctions only inside verified temporary roots and unlink the junction itself during cleanup without recursing into its target. Symlink cases may report a narrowly identified privilege limitation; junction coverage must still run and pass.
- Real cross-volume/removable-drive behavior needs a documented manual qualification if the hosted runner cannot supply it. Do not claim mocked cross-volume exceptions establish native cross-volume safety.

CI owner: Backend CI on native Windows, selected guarded filesystem tests under the private release interpreter, and integrated package checks for the new standard-library modules.

## HP-08: Serialized status polling and reconnection

### Transport and backend prerequisites

Extract `frontend/electron/bridge-transport.ts` so transport lifetime, pending requests, and error classification can be tested without an app window. Validate response envelopes before removing pending requests. A malformed identified response rejects that request with `protocol_error`; strict Python JSON serialization and fallback error generation remain inside the dispatch exception boundary. Backend exit/pipe loss rejects pending requests with `backend_exited`/`backend_unavailable`.

Give setup **status reads** a two-second main-process deadline; a timeout removes its pending entry and a late reply is ignored. Do not apply this retry policy to installation or other mutations. Reserve bounded control dispatch for status/cancel in `backend/desktop/protocol.py` so normal worker saturation does not queue status indefinitely. Control handlers only read state or set cancellation flags; they must not perform verification, network access, or wait for worker completion. Deduplicate outstanding status work per install so timed-out callers cannot accumulate blocked backend tasks.

Expose a narrow backend-state subscription through preload with an unsubscribe function, sanitized payload, and bridge-generation ID. On known exit, the UI moves directly to recovery instead of waiting for another poll. Do not expose arbitrary IPC subscriptions.

Add an active-install lookup and deduplication in `backend/desktop/installation.py`: repeated approval of the same still-active plan returns its existing operation; a conflicting setup plan reports `setup_busy`. Bind verification and settings application to the immutable plan context from HP-04. These are the necessary parts of B07/B08/B06 supporting recovery, not a claim that all broader transport, metadata-timeout, or queue-capacity findings are closed.

### Renderer state machine

Create `features/capabilities/useInstallStatus.ts` and a pure `installation-connection.ts`. Track **connection state separately from installation status**.

| State | Trigger | Behavior |
| --- | --- | --- |
| Connected | Valid current-generation status | Render actual progress; schedule next read 1.2 seconds after the prior one settles |
| Reconnecting | First transient status timeout/communication error | Start a monotonic 30-second window; show reconnecting feedback and elapsed time |
| Connected again | Valid response before deadline | Clear retry timers; apply current server status without resubmitting installation |
| Recovery required | 30 seconds elapse, confirmed bridge exit, or incompatible protocol | Stop automatic reads for that recovery window; retain last known progress with outcome explicitly unknown |
| Awaiting settings choice | Server reports HP-04 conflict | Present conflict resolution; do not treat it as connection failure or reinstall |
| Settled | Backend confirms completed/failed/cancelled | Show that actual result and refresh the appropriate capabilities/settings once |

During reconnection, wait 1, 2, 4, then 8 seconds between completed failed checks, capped at 8 seconds and by the remaining window. Each attempt's deadline is the lesser of two seconds and remaining time. Never allow attempts or outstanding UI updates beyond the 30-second window. Request identity, install ID, and bridge generation must match before applying a response. Unmount, new operation, resolution, or cancellation of the observer clears timers/subscriptions.

Recovery actions:

- If the process may still be alive, **Retry connection** starts a fresh bounded status-only window. It does not mean restart installation.
- If the backend exited, offer an explicit app restart; use the existing bounded shutdown/relaunch lifecycle. No automatic child-process restart or mutation replay is planned.
- After restart, recheck verified components and show only remaining setup needs. A fresh inspectable plan and explicit user action are required before further installation. Never erase completed downloads merely because the old operation ID is unavailable.
- If an install-start response was lost while the backend lives, query active setup before offering another approval. Cancellation acknowledgement loss leaves its outcome unknown until reconciled; do not claim cancellation succeeded merely because the button was clicked.

### Tests and exit criteria

- New `bridge-transport.test.ts`: timeout cleanup, late replies, malformed success/error envelopes, partial input, serialization errors, exit during a request, and no replay of mutation requests. Extend `ipc-response.test.ts` and Python protocol tests for structured codes/details.
- New `useInstallStatus.test.tsx` and `installation-connection.test.ts`: fake monotonic time, at most one caller request, exact 30-second boundary including pending reads, delay backoff, reconnect success, immediate known-exit recovery, unmount cleanup, stale install/generation replies, conflict status, failed cancellation, explicit Retry, and no double completion notification.
- New `frontend/scripts/smoke-recovery.mjs` with an offline Python fixture: drop/delay status replies, saturate ordinary workers, recover within the window, keep silence through a real 30-second window, and exit the backend. Assert actual user feedback, responsiveness, no second install worker, preserved synthetic completed-component files, and clean app shutdown.
- Run one real-time 30-second case natively; use fake clocks for the many unit permutations. Do not globally shorten production recovery constants to make CI pass.
- Check progress/conflict/recovery UI in both themes at supported minimum and normal window sizes, keyboard operation, and useful live-region updates without announcing every timer tick.

CI owner: Frontend Tests, Backend CI for control dispatch/installation ownership, and native recovery smoke. The package suite verifies production bridge/preload behavior without enabling a packaged test backdoor.

## Existing CI baseline and exact changes

Current pull-request/push workflows target `main` and also allow manual dispatch. Keep their existing trigger coverage and stable required-check names. A push to this feature branch alone does not automatically exercise the PR workflows; use a PR into `main` or manual dispatch when execution is separately requested.

| File | Current behavior | Planned update |
| --- | --- | --- |
| `.github/workflows/backend-ci.yml` | Windows, Python 3.12, full unittest discovery with coverage | New `test_*.py` suites join discovery automatically. Set isolated test app-data/work roots and offline component behavior; add explicit required Windows junction/subprocess checks that fail if their required scenarios did not execute. Produce coverage XML and a safety-case summary; upload sanitized reports on failure. Retain the current Python version rather than introducing an unrelated dependency-support migration. |
| `.github/workflows/frontend-tests.yml` | Windows, Node 22.12.0, Vitest coverage | Discover new Electron/helper/hook tests; add JUnit and coverage artifact output using `vitest.config.ts`. Keep fake timers local to recovery tests. Fail on unhandled promises and unexpected renderer errors. Do not set a blanket percentage target as a substitute for the required behavior cases. |
| `.github/workflows/frontend-quality.yml` | Version check, typecheck, lint | Existing checks cover the new modules/types. Extend lint/architecture coverage so changed native calls cannot bypass the typed client or central IPC registration. No unrelated action/runtime version bump. |
| `.github/workflows/electron-smoke.yml` | Build, app smoke, shutdown smoke, development package, packaged smoke | Build once, then run security, state, and recovery smoke scripts against that build in addition to existing smoke/shutdown. Extend package smoke with production navigation/sender/sandbox checks and hostile dev-URL handling. Increase timeout from 30 to 45 minutes for the new bounded native cases; give individual scripts their own smaller deadlines. Upload traces/screenshots and case summaries on failure, even when a preceding step fails. |
| `.github/workflows/release.yml` | Full suites, build/smoke/shutdown, audited private runtime, installer, packaged smoke, then tag/publish | Add all new native suites before packaging; run the selected standard-library safety tests with private Python; run enhanced packaged security smoke and a post-launch package/runtime audit **before** Tag release. All new gates use the existing unpublished-release condition and must fail the release on error. Do not change release triggers or permissions. |
| `scripts/build_local_release.ps1` | Local equivalent of release validation without publishing | Mirror every new native/private-runtime/package gate with `Assert-NativeSuccess`; retain work files on failure and restore environment variables in `finally`. |
| `.github/workflows/deploy-pages.yml` | Manual deployment of a released product site | No change; documentation planning and application repair do not authorize deployment. |

### New test commands and script integration

Add these package scripts when their implementations land:

```text
smoke:security  -> node scripts/smoke-security.mjs
smoke:state     -> node scripts/smoke-state.mjs
smoke:recovery  -> node scripts/smoke-recovery.mjs
```

They assume `npm run build` already succeeded. Keep `npm run smoke` as the existing build-plus-basic-smoke command. CI, release, and the local release script invoke the new scripts sequentially after that build and before packaging. Do not make unit tests depend on a previously running Electron process.

Add `tests/run_private_safety_tests.py` as an explicit test runner for the new filesystem/locking/transaction modules that are designed to use only the standard library. It adds only the repository test/source path explicitly and runs the selected suites under private Python with isolated mode, no site packages, and bytecode disabled. It must fail if a processing package is imported. Test fixtures are never copied into the installer; existing `electron-builder.yml` production file filters must continue excluding `tests/` and frontend smoke scripts.

Add `tests/run_windows_safety_tests.py` to run the mandatory native cases from `test_windows_destination_guards`, `test_publication`, and `test_policy_transactions`. It must fail on skipped mandatory junction, target-swap, or independent-process cases and write executed case IDs/results to a supplied JSON report. Backend CI runs `python tests/run_windows_safety_tests.py --report test-results/windows-safety.json` after full discovery. This intentionally repeats the small required native subset to make missing/skipped coverage a hard gate, not an assumption based on overall test count. Each new Electron smoke script writes its own case summary under `frontend/test-results/` and exits nonzero if any required scenario is absent or fails.

Generate backend coverage XML with `python -m coverage xml -o test-results/backend-coverage.xml`. Frontend Tests invokes `npm run test:coverage -- --reporter=default --reporter=junit --outputFile=test-results/frontend-junit.xml`; retain the existing V8 coverage reporters. Artifact steps use `if: failure()` and explicit report/trace/screenshot paths rather than uploading arbitrary temporary roots. Update the local release script and Release workflow to call the same mandatory Windows runner; invoke the private runner as `python.exe -I -B <absolute-repository-path>/tests/run_private_safety_tests.py` using the audited private executable.

Extend `frontend/scripts/smoke-packaged.mjs` rather than relying solely on mocked `app.isPackaged`. Its existing fresh-data/Unicode/private-Python checks remain. In release/local validation, run `npm run audit:package -- --require-bundled-runtime` again after packaged launch, and verify runtime hashes/forbidden components. The PR development package remains explicitly different from the private-Python installer; it cannot stand in for release-runtime verification.

### Deterministic, isolated, and safe CI fixtures

- Use a unique temporary root for each case and consistent profile identity for the two-launch single-instance case. Sanitize inherited `CENSOR_*`, `PYTHON*`, model-cache, and renderer URL overrides, except those intentionally injected by a named test.
- Development tests select the intended CI interpreter explicitly; packaged private-runtime checks must not gain readiness from ambient tools. All runtime/model installation calls in fault-injection tests are mocked. Dependency installation by CI bootstrap remains separate from exercising the app's consent flow.
- Keep fixtures under `tests/fixtures/` or frontend test helpers. A harness may substitute the backend or intercept Electron dialogs/native launching from the test process; do not add a renderer-accessible fault-injection API or a packaged environment flag that disables security.
- Use real process boundaries and barriers for locking/race claims. Mock expensive encoders and verifier results while exercising actual file creation/publication. Do not replace native filesystem operations with mocks in the tests claiming Windows race protection.
- Detect leaked children, locks, pending promises, and timers. Every native script closes the app/server in `finally`; cleanup resolves its own temp roots and never follows a junction into an outside fixture or user directory.
- Permit loopback fixture traffic only during runtime security tests; fail unexpected app download/install calls. `HF_HUB_OFFLINE=1` is useful but is not a complete network-blocking guarantee.
- Store only synthetic paths/content in traces and summaries. Never upload profiles, transcripts, dictionary snapshots/journals, cookies, model caches, or user media as generic test artifacts. Retain failure reports for seven days, consistent with existing smoke artifacts.
- No `continue-on-error` for safety suites, no blanket skips for Windows junctions, and no retries that turn a race failure into an accepted green run. A deliberately privilege-limited symlink test must state its limitation in the report.

## Final validation and acceptance matrix

These commands are future implementation validation, not commands executed to produce this planning document.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

From `frontend/`, after installing the documented development dependencies:

```powershell
npm test
npm run typecheck
npm run lint
npm run version:check
npm run smoke
node scripts/smoke-shutdown.mjs
npm run smoke:security
npm run smoke:state
npm run smoke:recovery
```

Then run the updated local release validation or the separately authorized release-equivalent CI validation for private Python, installer auditing, and packaged checks. Do not dispatch the current Release workflow merely to test this plan: it can tag, publish, and deploy.

| Issue | Required evidence before closure |
| --- | --- |
| HP-01 | Every channel rejects foreign senders/frames; native development and real packaged security checks pass |
| HP-02 | Valid output playback works; executable/outside paths and export bypasses never reach OS operations; rejected exports preserve sentinels |
| HP-03 | Thread/process edit races and journal crash recovery pass; native second launch focuses the only instance |
| HP-04 | Setup/locate preserves newer preferences and pauses conflicting runtime writes without reinstalling |
| HP-05 | Source identity and new artifact naming implemented after separate authorization; legacy mapping and representative hardware qualification remain open |
| HP-06 | All affected entrypoints pass common failure/cancel/collision/replace safety cases; shutdown regressions remain green |
| HP-07 | Actual Windows root/child junction and target-swap cases pass, including cleanup and archive/submission races |
| HP-08 | Real and fake-time reconnection cases pass; no silent progress stall, installer replay, or loss of valid completed downloads |
| HP-09 | Wizard patch/merge/conflict cases and a real backend update between steps pass; drafts and step state survive |

Run the full relevant suites on the final integrated revision, not only on isolated feature commits. CI artifacts should identify the commit, interpreter/Electron versions, executed case IDs, and any explicitly permitted environment limitation. Keep the prior lifecycle regressions; new modularization must not undo their protections.

## Release limits, compatibility, and handoff

- Existing settings and dictionary formats remain readable. New local lock/journal/root-binding metadata requires explicit recovery tests and documentation. An older application version does not understand the new transaction ownership; do not run old/new versions concurrently against one profile or claim downgrade safety without qualification.
- Complete model accuracy, real GPU/codec combinations, live YouTube authentication, clean-machine install/upgrade/uninstall, antivirus interference, and real removable/network-filesystem behavior are not proven by these synthetic CI cases. Document the remaining manual qualification results before release.
- If handle-based containment/publication cannot satisfy a native race test on a filesystem, keep that operation blocked there and report the limitation. Do not weaken the tests or claim that repeated path resolution eliminates every time-of-check/time-of-use race.
- Update the decision register and original review follow-up sections only after evidence establishes each fix. Add module ownership notes to `backend/README.md` and `frontend/src/README.md`, and align user-facing troubleshooting with actual conflict/recovery behavior.
- Keep B09 diagnostics/history limits, broad metadata subprocess bounds, other dictionary editor recovery issues, nested-root policy, and remaining medium findings visible unless explicitly addressed as part of a dependency above. This plan does not relabel them all fixed.
- Suggested implementation commit groups follow the delivery table; actual commits/pushes and release actions still require the user's task-specific authorization.

## Planning validation performed

Read the decision register, current backend/frontend owners, existing test suites and fixtures, package scripts, Windows CI workflows, release workflow, and local release validation script. Checked relevant Electron APIs against installed typings and primary documentation. This document was checked for issue coverage and valid local source links. No new regression suite, application change, workflow edit, download, media operation, or release action was performed.
