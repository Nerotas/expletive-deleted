# Single-File Actions and Selective Serial Queue

## Summary

Add explicit per-file processing actions and checkbox-based batch selection while retaining the one-at-a-time executor. **Transcribe + Transcode** is one staged job with a mandatory transcription gate: transcoding cannot begin until a compatible transcript has been successfully validated and persisted.

## Implementation Changes

### Mandatory transcription gate

- For `censor` jobs, enforce this sequence:
  1. Load and validate a compatible cached transcript, or create a new transcription.
  2. Validate transcript structure, model/library profile, audio source, and word timestamps.
  3. Persist new transcripts atomically and verify the saved artifact.
  4. Detect configured profanity.
  5. Begin censor/transcode processing.
- Treat an empty but valid transcript as successful for media containing no speech.
- Make transcript write or verification failures fatal. Never continue to transcoding with only an unsaved or malformed in-memory result.
- Preserve an existing transcript until its replacement has been written successfully.
- If transcription fails, leave the source intact, remove temporary transcript/output files, create no media output, and return an actionable retryable job error.
- Report-only jobs reach `transcribed` status only after the transcript artifact passes the same validation.

### Backend queue and desktop interface

- Keep `JobManager` at one worker so jobs execute sequentially in submitted order.
- Reject duplicate non-terminal jobs for the same resolved source while allowing retry after failure or cancellation.
- Add `jobs.submit_many`:
  - Request: `{ sources: string[], mode: "report_only" | "censor" }`
  - Ordered results:
    - `{ source, status: "queued", job }`
    - `{ source, status: "rejected", code, detail }`
  - Queue valid sources without rolling them back when another selection is rejected.
- Use rejection codes for unavailable, unsupported, outside-input, already-queued, and existing-output cases.
- Keep `jobs.submit` for single-file actions and `jobs.cancel` for running or waiting jobs.
- Permit atomic imports while processing. Imported files appear in Ready but are not automatically queued.
- Preserve archive safeguards: archive only verified transcribed/finished sources while the queue is idle, and never overwrite an archive target.
- Do not change settings schemas or existing job modes.

### Queue interface

- Add a stable per-file Actions group:
  - **Transcribe only** → create and verify the transcript, then stop.
  - **Transcribe + Transcode** → perform the mandatory transcription stage, then censor/transcode.
  - **Archive** → move a verified transcribed/finished source to Processed.
- Ready files may use the combined action because transcription is its first required stage.
- Transcribed files reuse their compatible cached transcript before transcoding.
- Disable processing actions for queued/running files and show **Remove from queue** for waiting jobs. Retain the top-level Cancel action for the running job.
- Add checkboxes for eligible Ready files, Select all/Clear controls, and:
  - **Queue transcript only**
  - **Queue transcribe + transcode**
- Submit selections in displayed path/name order. Clear successfully queued selections, retain rejected selections, and show a combined result.
- Track running and waiting jobs separately and display Ready, Queued, Active, Transcribed, and Finished counts.
- Keep required actions accessible at narrow widths with keyboard labels, visible focus, and disabled-state explanations.

## Test Plan

- Verify transcoding is never invoked when:
  - Whisper transcription fails.
  - Transcript data is malformed or incompatible.
  - Transcript persistence or post-write verification fails.
- Verify valid cached and newly generated transcripts unlock transcoding, including a valid zero-word transcript.
- Verify failed/cancelled jobs preserve source media and valid prior transcripts while removing incomplete artifacts.
- Verify selected jobs run sequentially, partial batch submission works, duplicates are rejected, and waiting jobs can be removed independently.
- Verify imports complete safely during another job and archive/path/output collision safeguards remain intact.
- Add renderer tests for all row actions, selection order, partial results, waiting-job controls, and action eligibility.
- Run backend tests and frontend test, typecheck, lint, build, and Electron smoke checks; visually inspect light/dark and narrow/wide layouts.
- Update user documentation and create `docs/single-file-selective-queue-report.md` with implemented behavior and validation.

## Assumptions

- “Transcribe + Transcode” means the existing profanity-detection and censored-output pipeline.
- A persisted, validated transcript is mandatory before transcoding.
- Queue state is session-only.
- Pause, drag-to-reorder, and automatic queueing after import are outside this version.
- Explicit row and batch actions override the saved default processing mode.
- Existing uncommitted profanity-list fixes and unrelated worktree changes must be preserved.
