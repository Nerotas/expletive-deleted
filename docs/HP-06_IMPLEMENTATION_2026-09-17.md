# HP-06: Verified output publication

`backend/filesystem/publication.py` owns exclusive staging, verification, flushing, cancellation, destination conflicts, replacement, and cleanup. Desktop jobs, batch/single-file CLI processing, downloads, transcript writes, imports, and archive/restore use it or its guarded file operations. Staging retains the media suffix for FFmpeg and remains inside a leased destination.

New output uses a collision-refusing native rename. Cleanup targets only the captured staging identity. Media must be nonempty and pass stream verification; copies check byte count and source stability; transcripts retain schema/model/channel validation. These checks do not establish transcription accuracy or introduce HP-05 source fingerprints.

Desktop submission captures source and authorized-output versions before queueing. Replacement rejects changed targets. The old file stays pinned, moves to a unique recovery name, and is retired only after publication. Failure restores it when possible; a competing destination is preserved and the error identifies the recovery file. This is not a single atomic swap. Abrupt termination can leave a hidden `.recovery` file for manual recovery; it is not disposable staging.

Archiving follows successful output publication. Archive failure reports that output was saved and retains the source. Same-volume archive/restore renames the pinned original; cross-volume handling copies/verifies before deleting it. The advanced single-file CLI requires `--overwrite` for replacement.

## Tests and CI

Publication tests cover new/replacement output, empty output, aliases, verification/cancellation/flush errors, replacement recovery, changed targets, and collisions. Two independent Python processes race at a publication barrier; exactly one succeeds. Existing desktop, batch, download, library, settings, transcript, and service suites cover integrated callers.

Native graceful/forced shutdown uses the real JobManager and common publisher. Backend CI and private-runtime release/local validation explicitly run filesystem gates; full backend and shutdown tests remain enabled.

`python -m scripts.qualify_media_publication` uses already installed FFmpeg/FFprobe and temporary synthetic media. It verifies readable audio/video and cancellation after verification without changing prior output or leaving staging. It downloads nothing and passed locally.

Validation passed 290 backend tests, 122 frontend tests, type checking, lint, build, native renderer-security checks, and the real-FFmpeg publication exercise. The packaged private Python also passed all 18 filesystem/publication tests. Thirty repeated two-process publication races passed after adding a bounded retry for transient Windows directory sharing conflicts. Private-runtime tests suppress bytecode generation to preserve the audited runtime payload.

Windows qualification uses an unpacked application with its private Python runtime; this does not establish NSIS installation/uninstallation or native cross-volume/removable-drive qualification. Protected filesystem mutations currently fail closed outside Windows and on unsupported network paths. HP-05 identity migration remains deferred.

The final unpacked package passed the dependency audit and security smoke. Earlier repetitions intermittently reported Chromium `ERR_FAILED` before the redirect-prevention event was observed. Added event diagnostics retain evidence on recurrence; subsequent repeated runs passed, but the intermittent smoke-test failure has not been explained. No foreign IPC authorization succeeded.
