# Profanity Censor Project Summary

## Current Status

This repository contains the known-working Python profanity-censor pipeline and is being reconstructed as the backend foundation for the desktop application.

The master product and architecture direction is recorded in [docs/Profanity Censor Desktop App - Master Project Handoff.md](docs/Profanity%20Censor%20Desktop%20App%20%E2%80%94%20Master%20Project%20Handoff.md).

## Working Pipeline

```text
Media file
    -> faster-whisper large-v3 transcription
    -> word-level timestamps
    -> profanity detection
    -> FFmpeg censor filters
    -> censored output
```

The current CLI supports:

- Serial folder-based batch processing
- Report-only transcription and detection
- Stereo muting or karaoke cancellation
- Discrete center-channel handling for recognized surround layouts
- H.264 stream copy or detected encoder selection
- Reusable transcript caches
- FFmpeg and Whisper progress reporting

## Repository Layout

```text
backend/
  censor/engine.py       Proven transcription, detection, and censor engine
  jobs/batch.py          Serial folder batch orchestration
  runtime/environment.py Dependency, hardware, cache, and encoder discovery
  runtime/paths.py       Runtime folder ownership

resources/               Curated censor and exclusion word lists
scripts/                 Bootstrap and maintenance commands
tests/                   Backend regression tests
docs/                    Product and architecture handoff

batch_process.py         Legacy-compatible batch entry point
censor_profanity.py      Legacy-compatible single-file entry point
workflow_runtime.py      Legacy-compatible runtime module alias
setup.py                 Legacy-compatible bootstrap entry point
```

The root compatibility files remain intentionally thin. New backend code should import from `backend`, not from those wrappers.

## Runtime Folders

The current CLI uses repository-relative folders:

```text
ready/       Input media
finished/    Censored output
processed/   Sources archived after successful CLI processing
transcripts/ Reusable transcript artifacts
```

These are temporary CLI defaults. The desktop settings layer will later provide the Windows Documents defaults and user-selected paths described in the master handoff.

## Commands

```powershell
python setup.py --install-system-dependencies
.\.venv\Scripts\python.exe batch_process.py --list
.\.venv\Scripts\python.exe batch_process.py
.\.venv\Scripts\python.exe batch_process.py --report-only
.\.venv\Scripts\python.exe -m unittest tests.test_runtime
```

Package entry points are also available for backend development:

```powershell
.\.venv\Scripts\python.exe -m backend.jobs.batch --list
.\.venv\Scripts\python.exe -m scripts.bootstrap --help
```

## Next Architecture Milestones

1. Add persistent validated settings and user-directory defaults.
2. Formalize jobs, statuses, structured events, and cancellation.
3. Add dependency and capability service operations.
4. Add the local authenticated service boundary.
5. Build the Electron and React Queue and Settings UI.

The existing engine should remain the behavioral baseline while those layers are added.
