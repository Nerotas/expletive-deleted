# Expletive Deleted Project Summary

## Current Status

This repository contains the Python profanity-censor pipeline, local application service, and Electron/React desktop application.

The master product and architecture direction is recorded in [docs/Profanity Censor Desktop App - Master Project Handoff.md](docs/Profanity%20Censor%20Desktop%20App%20%E2%80%94%20Master%20Project%20Handoff.md).

The Windows installer bundles only private CPython and its pip bootstrap. The consent-driven processing-component policy and release audit are recorded in [docs/BUNDLED_RUNTIME_PACKAGING_PLAN.md](docs/BUNDLED_RUNTIME_PACKAGING_PLAN.md).

HP-03 serializes complete policy reads and mutations across threads and processes, journals split-store publication, and recovers before returning snapshots. Electron claims one per-user instance before creating a window or Python bridge. Native state smoke also verifies CLI edits while the desktop runs. See [HP-03 implementation](docs/HP-03_IMPLEMENTATION_2026-09-23.md).

## Working Pipeline

Desktop shutdown requests cancellation before ending Python and waits up to 15 seconds. A Windows Job Object contains the bridge's process tree for forced-exit cleanup. Shared publication verifies and flushes staged output before a collision-refusing rename. Authorized replacement retains the previous file for recovery until publication succeeds. Settings changes and archive operations share a lock with submissions and reject conflicting active work.

HP-01 validates every IPC caller and restricts Electron navigation, sandboxing, and CSP. HP-07 binds configured folders to persistent filesystem identities and pins Windows paths during operations. HP-06 integrates those protections across jobs, imports/downloads, transcripts, and archive/restore. See the [implementation reports](docs/HP-06_IMPLEMENTATION_2026-09-17.md) for validation and platform limits. HP-05 source identity and legacy migration remain deferred.

HP-02 restricts playback to backend-derived, verified outputs and binds dictionary import/export to native file selections. Expiring leases protect the playback handoff; exports reject changed destinations. See [HP-02 implementation](docs/HP-02_IMPLEMENTATION_2026-09-17.md).

```text
Media file
    -> faster-whisper large-v3 transcription
    -> atomic transcript persistence and post-write validation
    -> word-level timestamps
  -> verified transcript queue entry
  -> profanity detection and FFmpeg censor filters
  -> censored output
```

The current desktop and backend application supports:

- Explicit single-file transcription, transcript-first censoring, and archival actions
- Checkbox-based selective transcription from Ready and selective censoring from Transcribed
- An opt-in automatic handoff from a verified transcript to the censor queue
- An opt-in YouTube download to transcription to censor-queue workflow
- Separate download, copy, transcription, and censor queue states
- A shared resource slot for transcription and censoring to prevent CPU, GPU, and storage contention
- Ready, Queued, Active, Transcribed, and Finished filtering with queue positions
- Partial batch acceptance with structured per-file rejection codes
- Report-only transcription and detection
- Stereo muting or karaoke cancellation
- Discrete center-channel handling for recognized surround layouts
- Source-video preservation by default and explicit H.264 encoder selection
- Reusable transcript caches
- A mandatory persisted-transcript gate before any censor/transcode work
- FFmpeg and Whisper progress reporting

## Repository Layout

```text
backend/
  censor/                Processing coordinator, transcripts, audio metadata, FFmpeg, and CLI
  desktop/               Private protocol, request routing, dictionary and setup controllers
  jobs/                  Serial job manager, records, events, and batch compatibility
  service/               Library, import, archive, settings, and capability boundary
  runtime/               Dependency contracts/inspection/plans/install, devices, encoders, timing
  runtime/paths.py       Runtime folder ownership
  policy/                Versioned, atomic user dictionary
  settings/              Validated schema, atomic store, and path checks

resources/               Curated censor and exclusion word lists
scripts/                 Bootstrap and maintenance commands
frontend/                Electron host, typed preload boundary, and React renderer
tests/                   Backend regression tests
docs/                    Product and architecture handoff

batch_process.py         Legacy-compatible batch entry point
censor_profanity.py      Legacy-compatible single-file entry point
workflow_runtime.py      Legacy-compatible runtime module alias
setup.py                 Legacy-compatible bootstrap entry point
```

The root compatibility files remain intentionally thin. New backend code should import from `backend`, not from those wrappers.

The [backend module guide](backend/README.md) documents ownership and import boundaries. Runtime compatibility facades retain established imports; optional speech packages load when capabilities or processing require them.

## Persistent Settings

Settings default to `%LOCALAPPDATA%\ExpletiveDeleted\settings.ini`. It is created automatically from validated defaults, remains outside the repository, and has a tracked [`config.example.ini`](config.example.ini) schema template.

First-run state is stored with the settings as `onboarding.completed` and `onboarding.last_step`. The Electron walkthrough resumes only an unfinished setup at its last saved section. Its six focused renderer sections live in `frontend/src/features/onboarding/`; settings, dictionary, import, and queue behavior remain owned by their existing feature/backend boundaries.

The live user dictionary is stored in `%LOCALAPPDATA%\ExpletiveDeleted\dictionary\censored.json`, `exclusions.json`, and `discovered.json`. Shipped files under `resources/` seed the classified stores on first use and supply explicit restore-defaults behavior only. Upgrades do not silently merge changed defaults into an existing user's policy. A combined JSON document is used only for explicit import and export.

User working directories default to:

```text
Documents\Expletive Deleted\Ready
Documents\Expletive Deleted\Finished
Documents\Expletive Deleted\Processed
Documents\Expletive Deleted\Transcripts
```

All four paths are independently configurable and validated. The application keeps source media by default. Manual archival is available after a verified transcript or output exists and the source has no queued or active job. Unrelated queued or processing files do not block archival.

## Commands

```powershell
python setup.py --install-system-dependencies
.\.venv\Scripts\python.exe batch_process.py --list
.\.venv\Scripts\python.exe batch_process.py
.\.venv\Scripts\python.exe batch_process.py --report-only
.\.venv\Scripts\python.exe manage_settings.py show
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Package entry points are also available for backend development:

```powershell
.\.venv\Scripts\python.exe -m backend.jobs.batch --list
.\.venv\Scripts\python.exe -m scripts.bootstrap --help
```

## Current Architecture Guarantees

Renderer module ownership, state rules, and validation commands are documented in the [frontend developer guide](frontend/src/README.md). The [frontend review](docs/FRONTEND_REVIEW_2026-09-16.md) records the page modularization and remaining setup/error-recovery risks.

1. Jobs, statuses, structured events, and cancellation are owned by the backend.
2. Queue execution is session-only. Copy and download work use separate lanes; transcription and censor work are independently queued but share one heavy-processing resource slot.
3. Electron exposes a narrow validated bridge; the renderer uses the typed desktop client.
4. Transcoding cannot begin until a compatible transcript has been persisted and verified from disk, including a fresh full-file SHA-256 match against the source held under a Windows read lease. Polling never hashes media. New names retain the input extension; finished media records source, transcript, output fingerprints, and processing settings in a provenance companion. Legacy artifacts remain unverified until an explicit decision; no migration or automatic retranscription occurs. See [identity behavior and benchmarks](docs/SOURCE_IDENTITY_DISCUSSION_2026-09-25.md).
5. Source media is retained on failed or cancelled work, and incomplete output is removed when safe.

HP-04 uses the shared settings transaction mechanism for component setup, normal Settings, and onboarding saves (the shared foundation for HP-09). Field-level comparisons preserve newer unrelated values and return conflicts without publication. Verified setup assets remain available while choices, active media work, or persistence errors delay settings application. See [HP-04 implementation](docs/HP-04_IMPLEMENTATION_2026-09-24.md).

HP-08 separates installation progress from connection state. Setup uses serial bounded status reads, a monotonic 30-second reconnection window, status-only reconciliation after lost acknowledgements, and explicit restart recovery. Backend control dispatch stays responsive under ordinary worker saturation. The offline native recovery gate runs in CI, release, and local validation; see [HP-08 implementation](docs/HP-08_IMPLEMENTATION_2026-09-24.md).

HP-09 completes the onboarding side of the shared settings transaction. The wizard owns a persisted baseline and an independent draft, allowlists its controls, explicitly compares progress, and advances only after a resolved save. Normal Settings retains its complete-draft contract and unsaved edits across wizard saves. Late picker results remain editable; repeated conflicts reset choices while preserving dialog focus restoration. See [HP-09 implementation](docs/HP-09_IMPLEMENTATION_2026-09-24.md).
