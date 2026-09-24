# HP-03: Dictionary transactions and one desktop owner

Dictionary reads and edits now share ownership across desktop request threads, independent store objects, background discovery, and CLI processes. A second desktop launch restores and focuses the existing window without creating another window or Python bridge, including a launch received during startup.

## Persistence contract

`backend/filesystem/locking.py` owns a registry of canonical-path reentrant thread locks plus a permanent OS lock file. Windows uses nonblocking `msvcrt.locking` on a fixed byte; POSIX uses `flock`. Acquisition has a five-second deadline, returns `store_busy` with retry guidance, and releases automatically on process death. Nested calls do not reacquire the OS lock. Lock files are never removed on release.

`backend/policy/transactions.py` wraps complete reads and mutations. The store stages managed writes in memory, so nested reads see the intended transaction. Before any publication, every affected payload and the resulting classification are validated. A flushed, atomically replaced `.policy-journal.json` records a transaction UUID and intended payloads for only `censored.json`, `exclusions.json`, and `discovered.json`. Publication replaces stores and removes the journal before success is acknowledged. Readers recover under the same lock before exposing any snapshot, including targeted reads and export snapshots.

Recovery rejects invalid JSON/UTF-8, duplicate fields, invalid envelope/version/UUID, unapproved destinations, redirected destinations, malformed entry metadata, and contradictory classifications before writing. An invalid journal or recovery I/O failure retains recovery data and reports `dictionary_recovery_required`; it never seeds defaults over that failure. An interrupted request may have committed and must be reconciled by reloading before retrying. Journal content is local sensitive data, omitted from routine errors and CI artifacts, and ignored by Git.

The existing split JSON schemas, paths, timestamps, and provenance remain intact. Targeted reads retain independence from unrelated corrupt stores when no recovery is pending. Import and restore remain intentional whole-policy replacements at their serialized position; edits that follow them survive. Import keeps its existing imported-source/new-import-time behavior. Recovery republishes the exact intended metadata without regenerating timestamps. Discovery excludes classified entries. Portable exports cannot replace managed stores, the lock, or the journal through either the CLI API or native picker flow.

## Desktop and CLI

`frontend/electron/single-instance.ts` claims the Electron lock before main startup. The loser quits before registering a startup callback. The owner keeps an early focus request until the window is ready, and restores/shows/focuses an existing minimized window. Development and installed launches use the same per-user `<application-data>/desktop` profile identity. Tests isolate that identity with `CENSOR_APP_DATA_DIR`.

`backend_app.py dictionary add|remove censor|exclude WORD` uses `PolicyStore` directly and starts no processing service. Expected dictionary errors print actionable guidance without a traceback. Processing continues to take its policy snapshot under the lock and release ownership before transcription or media work.

## Acceptance evidence and gates

- `tests/test_policy_transactions.py` uses barriers/events for same-store threads, separate stores, independent spawned Python processes, import/restore versus edit/discovery/export, and readers blocked during partial publication.
- Crash cases exit an independent process before the journal, after the journal, after every store replacement, before journal cleanup, and after cleanup. They cover initialization, classification, import, and restore, including provenance and timestamp checks.
- Corrupt-journal, fixed-destination, contradictory-payload, recovery-I/O retry, thread/process timeout, nested ownership, and lock-owner-death cases verify safe outcomes. Existing policy tests continue to verify formats, metadata, and targeted reads.
- `frontend/scripts/smoke-state.mjs` instruments the actual built main entrypoint at the Electron/child-process boundary. Real losing processes exit without windows or bridges; startup focus, minimized restoration, one owner, and concurrent actual CLI/desktop edits are asserted. Only case names/completion are written to the CI artifact.
- Backend CI explicitly requires transaction tests. Frontend test discovery includes lifecycle helper tests. Native state smoke is mandatory in Electron CI, release CI, `scripts/run_all_tests.ps1`, and `scripts/build_local_release.ps1`. Release validation also runs transaction tests with private Python. Native smoke cases remain sequential.

## Validation

Passed on the final implementation on Windows:

- Repository `.venv`: `python -m unittest discover -s tests -q` ? 311 tests.
- Existing private Python, with bytecode disabled: policy transaction, policy store, durable store, and native output-access suites ? 39 tests.
- `npm test` ? 150 tests across 11 files; `npm run lint`; `npm run build` (including TypeScript typecheck).
- Built Electron desktop smoke; native state smoke; native file authorization smoke; graceful and forced shutdown smoke; production and Vite development renderer-security smoke.
- Both changed PowerShell validation scripts parse successfully; `git diff --check` passes.

The first security-smoke attempt failed its existing redirect-event assertion (`ERR_FAILED` without `will-redirect`). An unchanged standalone retry passed production and development checks. No security assertion was removed or weakened. Native state smoke passed twice after correcting its instrumentation to compare Electron's PID rather than the Windows launcher PID.

## Limits

Process termination and injected publication failures are qualified on local Windows storage; sudden hardware power loss and network/removable-filesystem durability are not established by these tests. The POSIX locking branch is implemented but was not executed on this Windows host. Older application versions do not honor the new lock/journal and must not run against the same profile concurrently. This repair does not close settings/setup conflicts, bridge reconnect work, or other high-priority items. No installer was built or published as part of this task.
