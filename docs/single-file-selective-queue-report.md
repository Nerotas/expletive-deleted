# Single-File Actions and Selective Serial Queue Report

Date: 2026-08-31

## Implemented behavior

The desktop Queue now supports explicit actions for each eligible source:

- **Transcribe only** creates and verifies a transcript, then stops without media output.
- **Transcribe + Transcode** validates or creates the transcript before profanity detection and censored-output processing.
- **Archive** moves a source with a verified transcript or output to Processed while the queue is idle.
- **Cancel job** appears on the active row and uses the same cancellation path as the header's **Cancel active job** control.
- **Remove from queue** appears on waiting rows and cancels only that waiting job.

Eligible Ready files can be selected with checkboxes and submitted through **Queue transcript only** or **Queue transcribe + transcode**. Submission follows the displayed sort order. Accepted selections are cleared, rejected selections remain selected, and partial submission does not roll back accepted jobs.

The Queue displays separate Ready, Queued, Active, Transcribed, and Finished counts. It can filter by those states and sort by queue position, file name, or status. The running job displays **Active**; waiting jobs display `#1`, `#2`, and so on.

## Mandatory transcript gate

The censor engine no longer permits transcoding from an unsaved in-memory transcription. It now:

1. Loads a compatible cached transcript or runs Whisper.
2. Validates transcript structure, text, word timestamps, audio source, Whisper library, and model profile.
3. Writes a new transcript to a sibling temporary file, flushes it, verifies it, atomically replaces the destination, and verifies the saved destination.
4. Re-opens and validates the persisted artifact before profanity detection or FFmpeg processing.

An empty word list is valid for media containing no speech. A malformed, incompatible, unavailable, or unpersisted transcript stops the job before transcoding. Temporary transcript files and incomplete output are removed when safe, while source media and valid prior transcripts are retained.

The configured profanity list remains the processing source of truth. Vendor dictionary state is isolated and is consulted only for the explicit include-undiscovered workflow.

## Dictionary defaults

The desktop Dictionary and processing pipeline use the same complete, durable policy. Its factory defaults are shipped in:

- `resources/profanity_censor_words.txt` supplies the default censored words.
- `resources/profanity_exclusions.txt` supplies the default exclusions.

On first use, these files seed `%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json`. This versioned JSON document contains all censored words and exclusions. It is staged, verified, and atomically replaced; the resource files are never edited by the application. Existing legacy `policy.json` deltas are materialized once, and new shipped defaults do not alter an existing user dictionary.

There is no renderer-owned dictionary. The Dictionary page identifies the durable user-policy location, supports backend-owned import/export, and confirms before copying current factory defaults over it. It shows a loading state instead of temporarily presenting a pending request as an empty policy. Its query cache remains the only renderer snapshot, so reloading reflects the latest atomic backend policy.

Backend regressions cover seeding, persistence, migration, reset, import/export, malformed data, and interrupted writes. Renderer regressions verify durable metadata and confirmation before restore.

## Queue and bridge architecture

`JobManager` retains a single-worker executor. Accepted jobs are recorded in memory and submitted in request order, so only one transcription or FFmpeg process runs at a time.

`jobs.submit_many` accepts ordered source paths and a fixed existing job mode. Each source returns either a queued job or a structured rejection. Rejections cover unavailable sources, unsupported media, paths outside Ready, duplicates already queued or running, and existing output collisions.

Cancellation uses a per-job event. Waiting futures can be cancelled before execution. Active transcription checks cancellation between normalized segments, and FFmpeg progress handling terminates the child process when cancellation is requested. Cancelled work retains the source and removes incomplete output when safe.

Imports use temporary copies and atomic replacement and remain available while another job is active. Imported files appear in Ready but are not automatically queued. Queue records and positions remain session-only.

## Safety behavior

- Duplicate non-terminal jobs for the same resolved source are rejected; failed and cancelled sources can be retried.
- Existing output and archive destinations are never overwritten.
- Manual archive requires a verified transcript or output and an idle queue.
- Report-only status becomes Transcribed only after the transcript artifact exists and has passed validation.
- Failed or cancelled processing retains original media.

## Validation performed

Before the final row-level cancel control was added, the following validation completed successfully:

- Backend: `137` unit tests passed with `python -m unittest discover -s tests`.
- Renderer: `11` Vitest tests passed.
- TypeScript typecheck passed.
- ESLint passed.
- Production Electron/Vite build passed.
- Native Electron smoke test passed.

Renderer regression coverage includes per-file modes, displayed-order batch submission, partial results, queue positions, filtering, sorting, and independent waiting-job removal. The row-level cancel assertion was added afterward but was not rerun because active testing was paused at the user's request.

The later versioned policy-store correction was validated without media processing:

- `16` policy-store and desktop-bridge tests passed, covering atomic persistence, failed-write preservation, removals across default upgrades, mutually exclusive classifications, shipped defaults, and bridge responses.
- `10` focused runtime, profanity-detection, and serial job-manager tests passed.
- All `12` renderer tests in `App.test.tsx` passed, including resource-source visibility and the pending-load state.
- TypeScript typecheck and ESLint passed.

Visual review covered populated Queue states at wide and narrow widths in light and dark themes. The narrow table remains horizontally scrollable, and its accessibility snapshot retains the queue-position and Actions columns, including cancellation and waiting-job controls.

No real long-running media file was processed during validation; backend media operations used synthetic or mocked processors.
