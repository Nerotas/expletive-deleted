# Expletive Deleted Project Summary

## Current Status

This repository contains the Python profanity-censor pipeline, local application service, and Electron/React desktop application.

The master product and architecture direction is recorded in [docs/Profanity Censor Desktop App - Master Project Handoff.md](docs/Profanity%20Censor%20Desktop%20App%20%E2%80%94%20Master%20Project%20Handoff.md).

The proposed Windows runtime distribution change is recorded in [docs/BUNDLED_RUNTIME_PACKAGING_PLAN.md](docs/BUNDLED_RUNTIME_PACKAGING_PLAN.md). It is a plan, not current release behavior.

## Working Pipeline

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
  censor/engine.py       Proven transcription, detection, and censor engine
  jobs/                  Serial job manager, records, events, and batch compatibility
  service/               Library, import, archive, settings, and capability boundary
  runtime/environment.py Dependency, hardware, cache, and encoder discovery
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

1. Jobs, statuses, structured events, and cancellation are owned by the backend.
2. Queue execution is session-only. Copy and download work use separate lanes; transcription and censor work are independently queued but share one heavy-processing resource slot.
3. Electron exposes a narrow validated bridge; the renderer uses the typed desktop client.
4. Transcoding cannot begin until a compatible transcript has been persisted and verified from disk.
5. Source media is retained on failed or cancelled work, and incomplete output is removed when safe.
