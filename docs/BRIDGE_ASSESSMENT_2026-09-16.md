# Electron–Python bridge assessment — 2026-09-16

Assessed revision: `bcdeff60e7eca9a121745b4ccb4fad43a5c925b4` (merge of PR #67). The bridge/backend files match the previously validated `5dbc6a2` revision.

**Recommendation: address the four high-priority findings before treating the bridge as release-ready.** The architecture is workable and the recent shutdown fixes pass their native regressions. The remaining weaknesses concern privilege boundaries, concurrent writes, and recovery from stalled or malformed requests. Passing the existing suites does not cover these cases.

This assessment records findings and offline audit probes only. It does not fix application behavior, download processing components, or process user media.

Archive note: the findings, source locations, probe imports, and validation results below describe the assessed revision, not the latest branch. Subsequent backend and frontend refactors moved modules and changed some behavior. See the [backend review](PYTHON_BACKEND_REVIEW_2026-09-16.md) and [frontend review](FRONTEND_REVIEW_2026-09-16.md) for later work; committing this historical assessment does not revalidate every finding against those changes.

## Scope and architecture

The review covered the typed renderer client, preload, all eight Electron IPC channels, all 37 Python method branches, JSON-lines transport, runtime discovery, service and policy persistence, setup workers, job/download control, polling, error handling, and Windows process ownership. Downstream code was inspected where it establishes whether a bridge operation is safe.

```text
React feature → desktop-client.ts → context-isolated preload
  → Electron ipcMain → private stdin/stdout JSON lines
    → Python request executor (4 workers) → service/policy/setup handlers
      → job, download, and dependency-install workers
```

| Surface | Operations | Current boundary |
| --- | --- | --- |
| Settings/capabilities | Read settings, save settings, inspect readiness | Settings are validated and saved atomically; some multi-step callers still race. |
| Dictionary/reviews | Nine dictionary methods; transcript review | Local policy persistence; individual file writes are atomic, complete edits are not serialized. |
| Dependency setup | Plan, install, status, cancel, inspect/locate components | Install commands come from backend-created plans with approval-ID verification. |
| Library/archive | List, import, archive, restore, purge | Backend root checks exist; archival mutations do not share the submission lock. |
| Jobs/downloads | Submit, batch, list, get, events, cancel | Structured records and errors; synchronous metadata work precedes download registration. |
| Native IPC | Generic invoke, four pickers, external link, folder, file | Context isolation enabled; sender and selected-path authorization incomplete. |

TypeScript types help application callers but do not validate messages at runtime. Python rejects unknown method names and validates many individual parameters; there is no shared schema/version handshake for the complete protocol.

## Findings by priority

High means a demonstrated trust-boundary or user-state preservation defect. Medium means a correctness, recovery, privacy, or scaling defect with a narrower trigger. These are application priorities, not CVSS scores.

| ID | Priority | Finding | Evidence |
| --- | --- | --- | --- |
| B01 | High | Untrusted navigation retains privileged bridge access | Native Electron reproduction |
| B02 | High | File-opening and dictionary-export paths are not authorized by the main process | Native interception and temporary-file reproduction |
| B03 | High | Concurrent dictionary changes lose acknowledged edits | Deterministic concurrent reproduction |
| B04 | High | Setup completion overwrites newer saved settings | Deterministic concurrent reproduction |
| B05 | Medium | Archiving can move a source after it has been queued | Deterministic concurrent reproduction |
| B06 | Medium | A stalled metadata request blocks submissions/settings; request saturation delays cancellation | Source inspection and executor reproduction |
| B07 | Medium | The same install plan can launch overlapping setup workers | Scheduler reproduction; installation itself mocked |
| B08 | Medium | Malformed responses and serialization failures leave requests unresolved | Actual transport source and Python server probes |
| B09 | Medium | Unlimited stderr retention exposes sensitive diagnostics as user errors | Source inspection and transport reproduction |
| B10 | Medium | Setup polling silently ignores bridge failure and keeps showing active work | Source inspection |
| B11 | Medium | Queue polling repeatedly transfers every historical event | Source inspection; no long-session load benchmark |

### B01 — Untrusted navigation retains privileged bridge access

Locations: `frontend/electron/main.ts:138–159`, all `ipcMain.handle` registrations; `frontend/electron/preload.ts:8`; `frontend/index.html`.

IPC handlers ignore the sender/frame. There is no navigation guard or window-creation policy, the renderer sandbox is explicitly disabled, and the renderer document has no Content Security Policy. `ELECTRON_RENDERER_URL` is also honored without checking `app.isPackaged`.

**Reproduction:** launch the actual built Electron entrypoint with isolated app data, navigate the main window from the application to a harmless HTTP page served on loopback, then call the existing preload API from that page. Both `bridgePresent` and `settingsReadable` returned `true`. Observed preferences were `contextIsolation: true`, `nodeIntegration: false`, `sandbox: false`.

This demonstrates that a document outside the app's trusted UI can exercise the bridge once loaded. It does not establish an existing remote XSS or a way to force that navigation from media content. A renderer compromise or unexpected navigation would have substantially greater impact than intended.

**Remediation:** validate the specific trusted webContents, top-level frame, and application URL on every IPC channel; deny unexpected navigation/windows; allow the development URL only in development; enable the renderer sandbox and a restrictive production CSP. Electron's [security guidance](https://www.electronjs.org/docs/latest/tutorial/security) recommends sender validation, navigation restrictions, sandboxing, and CSP.

**Acceptance:** native tests reject foreign documents, frames, windows, and forged senders; ordinary routing and all supported pickers still work.

### B02 — Native file operations accept arbitrary renderer paths

Locations: `frontend/electron/main.ts:192–212`; `scripts/desktop_bridge.py:197–202`; `backend/policy/store.py:240–244,448–477`.

`openFile` forwards its argument directly to `shell.openPath`; it does not check the configured output root, media extension, resolved file, or symlink target. Dictionary export independently accepts any destination string and atomically replaces an existing file. The save dialog's selection and overwrite consent are not bound to the later export request.

**Reproduction:** `openFile('C:\\Windows\\System32\\cmd.exe')` reached the OS-opening function. That function was intercepted; no program was launched. A dictionary export to a temporary existing `original.mp4` succeeded and replaced its synthetic media bytes with dictionary JSON without using a picker.

This is bounded by the application's Windows account permissions and does not grant arbitrary file contents or shell-command interpolation. It does expose native launching and destructive writes beyond the advertised finished-file/dictionary workflow, especially in combination with B01.

**Remediation:** expose an output identity resolved by the backend instead of an arbitrary open path. Require an existing supported media file within the resolved output root. Bind import/export operations to main-process picker grants, validate file type and target, and preserve explicit overwrite consent. Avoid solving this solely through renderer checks.

**Acceptance:** executable, shortcut, outside-root, symlink/junction escape, and unapproved overwrite tests fail safely; user-approved dictionary exports remain supported.

### B03 — Concurrent dictionary changes lose acknowledged edits

Locations: `scripts/desktop_bridge.py:171–188,548–552`; `backend/policy/store.py:175–222`.

The four request workers share a policy store with no transaction lock. Each update reads the entire dictionary, modifies a snapshot, and writes it back. Atomic replacement prevents a torn individual JSON file, but does not prevent lost updates or inconsistent censor/exclusion snapshots across files. Multiple desktop instances also have no single-instance guard or cross-process policy lock.

**Reproduction:** pause two `dictionary.add` calls after both read the same policy. Let one finish, then let the other commit its stale snapshot. Both returned `changed: true`; only one of `auditone`/`audittwo` remained. An initial unconstrained Windows run also produced a sharing/access error during concurrent replacement.

**Remediation:** serialize complete policy transactions, including discovered words, import, restore, and first-use initialization. Address readers of the split files and multiple-process access, either with an appropriate persistence lock or enforced single-instance ownership.

**Acceptance:** simultaneous adds/removes/classification moves preserve all accepted changes; initialization and reads never expose inconsistent policy; a second app instance cannot bypass ownership.

### B04 — Setup completion overwrites newer saved settings

Locations: `scripts/desktop_bridge.py:106–124,316–352`; `backend/service/application.py:70–94`.

Setup reads all settings, changes runtime fields, and later submits the entire snapshot to `update_settings`. The lifecycle lock protects each save, not the read–modify–write sequence. Locate-existing handlers follow the same pattern. Two completed setup workers can also overwrite one another's component paths.

**Reproduction:** pause setup after its settings read, save `onboarding.completed = true`, then resume the setup save. Setup reported `completed`, but persisted `onboarding.completed` reverted to `false`. Installation was mocked; the real service validation/persistence path ran against a temporary store. The same mechanism can lose unrelated user preferences.

**Remediation:** provide a backend operation that patches only verified runtime fields while holding the settings transaction lock. Use settings revisions/conflict handling for complete user drafts. Do not allow setup to replace an old full snapshot.

**Acceptance:** concurrent user saves and component completions preserve both sets of changes; active-job rejection remains effective; failures retain the user's draft.

### B05 — Archive checks race with job submission

Locations: `backend/service/application.py:139–167,199–258`.

Archiving checks for active work before scanning the library and moving the source, but does not take the lifecycle lock used by submission and settings replacement. Restore and purge have similar check-then-mutate boundaries requiring review.

**Reproduction:** pause archive after its active-job check, queue the same source through the service, then resume archive. The source moved to Processed while its job was queued. The original remained preserved, but the job's expected Ready path no longer existed. The queue manager was stubbed to control timing; actual source movement used temporary files.

**Remediation:** serialize source-mutating operations with submissions/settings changes and revalidate source/destination immediately before mutation. Preserve collision protections.

**Acceptance:** an archive-versus-submit race either archives first and rejects submission, or queues first and rejects archive; never accept both against the old location. Add corresponding restore/purge cases.

### B06 — Synchronous metadata can stall the control plane

Locations: `backend/service/application.py:41–49,130–132`; `backend/jobs/downloads.py:108–129,336–354`; `scripts/desktop_bridge.py:548–552`.

`downloads.submit` holds the service lifecycle lock while yt-dlp metadata lookup runs synchronously. That subprocess has no timeout or registered job/cancellation handle yet. A stalled network/tool blocks subsequent settings saves and submissions. Requests waiting on the lock can occupy all four bridge workers, leaving cancel/status calls queued behind them.

**Reproduction:** occupy all four request workers with controlled blocked operations, then send `jobs.cancel`. It was not dispatched until the workers were released. The unbounded real metadata call and lock ownership are established by source inspection; no live YouTube outage was induced.

**Remediation:** register metadata retrieval as cancellable background work, or perform bounded lookup outside the transaction lock and revalidate at submission. Bound subprocess duration and request queues; preserve capacity for cancel/status. A client timeout alone must not make an ongoing mutation safe to retry.

**Acceptance:** a silent/hung metadata subprocess cannot prevent cancellation, status, or an actionable error. Closing remains bounded by the existing shutdown fallback.

### B07 — Duplicate setup requests launch overlapping installers

Locations: `scripts/desktop_bridge.py:45–49,264–301`; `backend/runtime/dependencies.py:529–576`.

Plans remain reusable and every `dependencies.install` creates a new install ID and executor task. The lock serializes scheduling, not execution; four setup workers can write shared component destinations concurrently. The UI tracks one install ID and is not a backend concurrency guarantee.

**Reproduction:** submit the same stored plan twice with scheduling intercepted. Two distinct install IDs and two worker submissions were produced. Actual duplicate package installation and any resulting filesystem damage were deliberately not performed.

There is also context drift: a model plan embeds the reviewed cache directory in its command, while the bridge resolves the current settings cache again at installation time and supplies it for verification/persistence. Changing the cache between planning and approval can download to the original approved directory but verify the new directory. This observation is source-derived; it is not an unapproved-command execution finding.

**Remediation:** serialize or deduplicate overlapping component installations, return the existing operation for a repeated request, and bind verification/persistence to immutable plan destinations. Reject stale plans when their context is no longer valid.

**Acceptance:** duplicate approvals cannot launch overlapping installs; conflicting plans are rejected or queued explicitly; a changed cache cannot redirect verification away from the approved result.

### B08 — Transport failures can leave promises unresolved

Locations: `frontend/electron/main.ts:74–96,109–121`; `scripts/desktop_bridge.py:528–546`.

The main process casts responses to a TypeScript type without runtime validation. It deletes a pending entry before reading the error payload, then silently catches malformed responses. Requests have no transport deadline. On the Python side, serialization/write happens outside the exception-to-response boundary, and executor futures are not observed.

**Reproduction:** run the actual TypeScript transport source with mocked Electron/child streams. A response `{"id":1,"ok":false}` removed the request from the pending map and then threw while reading the absent error object. Its promise remained unresolved even after bridge exit. Invalid JSON remained pending until exit. A Python handler returning a non-serializable value produced zero response lines and no surfaced dispatch error.

Additional gaps: no frame-size/in-flight bound or backpressure handling; Python permits non-finite JSON numbers by default; stdout uses independent chunk decoding. Current `json.dumps` escapes Unicode by default, so ordinary Unicode response values are not evidence of a current split-character bug. Request UTF-8 handling is already covered by regression tests.

**Remediation:** validate envelopes before removing pending entries, serialize inside the error boundary with strict JSON, always settle identified requests, and handle stream failures explicitly. Add method-appropriate deadlines, bounded buffers/queues, and operation IDs for ambiguous mutation outcomes. Do not automatically replay destructive mutations after a timeout.

**Acceptance:** malformed shapes/JSON, NaN, oversized frames, partial lines, broken pipes, no response, and bridge exit settle predictably without leaks or duplicate side effects.

### B09 — Stderr is unlimited and becomes a user-facing failure

Locations: `frontend/electron/main.ts:67–71,101–105`; `scripts/desktop_bridge.py:560–569`; `backend/censor/engine.py:789–815`.

Python redirects normal processing prints to stderr, including detected words and timestamps. Electron retains every stderr chunk in an unbounded string, then uses the entire accumulated text as the failure message on exit. Structured per-request errors are useful, but this exit path bypasses their separation of message and diagnostic detail.

**Reproduction:** inject a synthetic sensitive diagnostic through the real transport's mocked stderr stream, then exit. The pending request's error message was exactly that diagnostic. No user content was used.

**Remediation:** retain a bounded diagnostic tail, remove unnecessary content logging, provide a short actionable exit message, and expose redacted diagnostics separately on explicit request. Avoid writing transcript content into routine application logs.

**Acceptance:** noisy processing cannot grow retained diagnostics without limit; bridge failure messages do not contain detected words, transcript text, or unrestricted historical stderr. This is local exposure/retention, not evidence of remote telemetry.

### B10 — Setup polling hides loss of the bridge

Location: `frontend/src/features/capabilities/useCapabilities.ts:64–75,121–125`.

Status polling swallows every rejection and retains the previous `running`/`canceling` state. Cancellation errors are swallowed too. If Python dies during setup, the progress UI can remain active indefinitely and continue retrying; another query may display an error, but it does not settle this install state. Interval polling also permits overlapping unresolved requests.

**Evidence:** source inspection; existing renderer tests mock the typed client and do not exercise bridge death during setup.

**Remediation:** distinguish transient polling errors from service loss, report an interrupted/unknown operation state, prevent overlapping polls, and provide an explicit recovery path. Do not imply installation was rolled back merely because the connection was lost.

**Acceptance:** killing the bridge during setup gives an actionable interrupted state and stops unbounded polling; restart rechecks installed components before offering retry.

### B11 — Queue polling retransmits all event history

Locations: `frontend/src/features/queue/useQueue.ts:40–49,68–76`; `frontend/src/services/desktop-client.ts:95,101`; `backend/jobs/manager.py:190–198`; `backend/jobs/downloads.py:133–160`.

Each poll lists the library/archive/jobs/downloads, then requests every event for every retained job, including terminal jobs. Only the final event is retained by the renderer. Local jobs already support an `after_sequence` cursor, but the typed client does not send one; download events have no cursor. Backend histories have no retention bound.

**Impact:** polling costs and IPC payloads grow with session history, increasing allocation, JSON parsing, and control-request delay. This is established algorithmically by source inspection; no production-size memory/latency benchmark was run.

**Remediation:** batch current job state or latest events, use sequence cursors for detailed history, skip repeated terminal-job histories, and define bounded retention/pagination. Keep queue polling independent of settings reloads.

**Acceptance:** benchmark long jobs and many terminal jobs; per-poll work should track changed state rather than total historical events.

## Safeguards that are working

- Private child-process pipes avoid a listening HTTP server or network-accessible backend endpoint.
- Context isolation is enabled; Node integration is disabled; preload does not expose `ipcRenderer` itself. These help but do not address B01/B02.
- Python method dispatch rejects unknown names; job booleans/modes, dictionary pagination, and many paths are validated.
- Process launch uses argument arrays. Setup executes backend-built commands, and the install engine verifies the approved plan ID against its actions.
- Domain errors preserve useful codes/diagnostics through IPC; expected error handling has tests.
- Packaged runtime discovery prefers private Python, sanitizes inherited Python configuration, suppresses bytecode writes, and keeps processing-component downloads consent-driven when the runtime manifest is present.
- Local submissions/settings changes share a lifecycle lock; active downloads now block manager replacement.
- Closing sends EOF, cancels backend work, and waits up to 15 seconds. The Windows Job Object contains descendants after normal or forced bridge exit. Both native shutdown scenarios passed again during this assessment.
- New censored output is staged and verified before publication, protecting Finished from interrupted output.

## Additional design/test gaps

These are lower-confidence or lower-priority observations, separate from the eleven findings above:

- Missing runtime manifest returns an empty bundled-runtime selection and permits ambient Python fallback. That behavior is explicitly unit-tested for development packages, but the production installer should have a separate, explicit requirement that survives a missing/damaged manifest. No corrupted-install reproduction was run here.
- Startup probes are synchronous, have a 10-second timeout per interpreter candidate, and run before window creation. There is no startup readiness handshake or protocol-version negotiation. Measure startup under slow antivirus and inaccessible paths.
- Bridge loss requires restarting the app. Automatic mutation replay would be unsafe; recovery should first reconcile what completed. App instance ownership and recovery deserve an explicit design.
- Some destructive confirmation exists only in the renderer; sender validation and operation-specific grants should establish what the trusted main/backend boundary actually authorizes.
- Contract tests do not comprehensively compare all renderer methods/response types with Python handlers. Many tests mock one side; main-process framing, sender rejection, queue saturation, and connection-loss behavior need direct coverage.

## Validation and reproducibility

Run in this assessment:

- `python -m unittest tests.test_desktop_bridge tests.test_backend_service tests.test_process_lifetime` using `.venv`: **37 tests passed**.
- `npm test -- --run electron` from `frontend/`: **13 tests across 3 files passed**.
- `node scripts/smoke-shutdown.mjs` from `frontend/`: **graceful and forced native shutdown passed**.
- Native navigation/file-opening probe, Python concurrency/serialization probes, and the actual TypeScript transport under mocked streams produced the results recorded above.

The earlier full 266-backend/74-frontend validation, package audit, and packaged first-run smoke remain recorded in [the lifecycle follow-up](WINDOWS_LIFECYCLE_FOLLOWUP_2026-09-16.md); those full suites/package checks were not rerun for documentation-only changes here. The native assessment used the existing built entrypoint matching the assessed source, not an installed fresh-VM application.

Reproduction sources are in [bridge-assessment/](bridge-assessment/). They intentionally probe current failures, use temporary synthetic data and mocked installers, and intercept native file launching. They do not install dependencies, invoke a shell through the app, or use live YouTube. Native probes leave isolated audit data under ignored `frontend/node_modules/.tmp/` for inspection.

For historical reproduction, use a separate checkout of assessed revision `bcdeff60e7eca9a121745b4ccb4fad43a5c925b4`, copy these probe files into it, and prepare its documented development environment. The probes intentionally depend on that revision's private implementation details; they are not maintained regression tests for the current branch.

From that checkout's repository root:

```powershell
.\.venv\Scripts\python.exe docs/bridge-assessment/backend-probes.py
```

From that checkout's `frontend/`, with its matching production build available (`npm run build` if needed):

```powershell
node ../docs/bridge-assessment/native-probes.mjs
node ../docs/bridge-assessment/transport-probes.cjs
```

These are diagnostic reproductions, not a substitute for regression tests with corrected expectations. Controlled barriers establish possible interleavings; they do not estimate how often users encounter them.

Not exercised: external exploitation, installer tampering, real model inference or GPU behavior, live authentication/network failures, low-disk recovery, Windows session-ending/power-loss behavior, large-library load, or a full multi-instance stress test.

## Suggested repair order

1. Close native privilege gaps: trusted sender/frame checks, navigation policy, safe output opening, picker-bound exports.
2. Make mutations transactional: dictionary state, runtime settings patches, archive/submission serialization, and app instance ownership.
3. Make transport failures explicit: schema validation, complete promise settlement, deadlines, stream handling, and bounded diagnostics.
4. Keep control operations responsive: background metadata jobs, setup deduplication/context binding, failure-aware polling, and incremental event delivery.

Each group should have focused fault-injection tests and native Windows verification before a full regression/package pass. The audit itself makes no implementation changes.
