# Windows build audit — 2026-09-16

Release recommendation: **hold for the two lifecycle findings below**. Building and opening successfully does not establish safe behavior when a user closes the app during processing or changes settings during a download.

## Remaining findings

### High: closing the app bypasses processing cleanup

`frontend/electron/main.ts:213` kills the Python bridge immediately on `before-quit`. It does not request cancellation or wait for backend cleanup. On Windows, terminating the parent does not provide a graceful shutdown contract for its FFmpeg, yt-dlp, or setup subprocesses.

This matters because `backend/jobs/runtime.py:98` writes a new censored output directly to its final destination; the temporary-output path is currently used for replacements. `backend/service/library.py:89` marks any existing output as finished without validating completion. Closing during processing can therefore leave an incomplete file that appears finished after reopening, or a subprocess that keeps working after the window closes.

Evidence: source inspection of shutdown, job output handling, and library classification. This audit did not force-kill a real transcription or media encode. Address graceful cancellation/process-tree ownership and publish new outputs atomically only after verification. Add a native Windows close-during-processing regression before release.

### High: saving settings loses active download tracking

`backend/service/application.py:58` guards settings updates against local jobs but does not check active downloads. It closes and replaces the download manager. `backend/jobs/downloads.py:143` shuts down its executor without waiting or cancelling an already running task.

An offline reproduction with an active synthetic download record produced:

```json
{
  "settings_save_accepted_during_download": true,
  "download_manager_replaced": true,
  "old_manager_active_records": 1,
  "visible_download_records_after_save": 0,
  "network_used": false
}
```

The old worker can continue with its original paths while its progress/cancel controls disappear. Its completion callback can reach the newly configured local job manager. Prevent settings replacement while downloads are active, including concurrent submission/settings requests, and test both the guard and a completed download.

## Fixes made during this audit

| Issue | Change and validation |
| --- | --- |
| Windows pipe encoding corrupted Unicode request values | Configure bridge stdin/stdout as UTF-8. Regression starts with legacy `cp1252` streams and verifies accented/CJK paths survive. Packaged smoke saves a Unicode input path and checks the actual directory. |
| System Python environment could break private Python | Probe private Python in isolated mode and remove inherited `PYTHON*` configuration before setting the app's managed package path. Unit tests cover isolation; packaged smoke deliberately supplies invalid `PYTHONHOME` and unrelated `PYTHONPATH`. |
| Setup appeared finished after one component | Component completion leaves the overall installation running until every action verifies and settings persistence finishes. Regression checks status after both intermediate and final component callbacks. |
| An early setup cancellation was lost | Create the cancellation event before scheduling the worker, retain cancelled status, and leave terminal installs unchanged when cancellation arrives late. Regression exercises cancellation before worker startup. |
| Subfolder transcript reviews looked in the top-level transcript directory | Use the configured input root when resolving the transcript. Regression checks a nested source, an identically named top-level transcript, and rejection of an outside source. |
| A local installer command could omit private Python | `npm run package:win` now requires the runtime during staging and package auditing, regardless of CI environment flags. Confirmed that required staging rejects a missing source before modifying staged files. Development-only `package:dir` behavior remains available. |
| Launch modified the audited private runtime | A post-launch audit found six newly generated standard-library `.pyc` files. Disable bytecode writes for the packaged bridge, runtime probe, and verification command. Repeat the final package audit before and after launching the corrected build. |

Audit tooling now reports child-process launch failures instead of throwing on an undefined error string. Smoke tests fail on renderer exceptions instead of merely logging them. Packaged smoke isolates application-data overrides, checks Unicode paths, and tests without ambient processing tools. `PACKAGE_AUDIT_ROOT` allows auditing a separate build without replacing existing release artifacts.

## Validation

- Windows x64 host: OS build 10.0.26200; Node 24.12.0; repository Python 3.14.0; packaged private Python 3.13.15 and pip 25.2; Electron 44.0.0.
- Full backend suite: **254 tests passed** after the bridge fixes.
- Frontend/Electron/audit unit suite: **72 tests passed** after the final runtime fix.
- Production frontend build, TypeScript check, ESLint, version consistency, and whitespace validation passed.
- Native Electron smoke passed: onboarding, preload, settings, dictionary dialogs, routing, and dark navigation contrast. Light/dark screenshots were visually reviewed.
- Private Python executable and pip verification passed.
- A separate NSIS installer was built locally without publishing. The final packaged first-run smoke passed with the actual private interpreter and the hostile/Unicode environment described above.
- The final package dependency/file-hash audit passed **before and after launch**, including after executable Python/pip verification. No new runtime bytecode artifacts were created.
- Initial packaged first-run smoke passed under Unicode application-data paths, a restricted PATH, and conflicting system Python variables. The post-launch audit exposed the bytecode issue described above; it was not dismissed as a successful package audit.

Sandbox restrictions initially prevented build-tool child processes and stalled temporary-file tests. Those checks were rerun outside the sandbox. These were validation-environment failures, not application failures.

## Coverage limits

The installer was built, but it was not installed/uninstalled or upgraded on a clean VM. No processing packages, media tools, or speech model were downloaded through onboarding. Real large-v3 inference, GPU/driver combinations, live YouTube authentication, offline/proxy setup, antivirus interference, low-disk conditions, and long-running cancellation still need an end-to-end release test. The host's development Python differs from the packaged version; packaged startup exercised the actual private interpreter, but the complete backend unit suite ran in the repository `.venv`.

The initial audit installer was **NotSigned** according to Windows Authenticode inspection. Builder messages saying “signing with signtool.exe” do not establish that an installer received a trusted signature. Final signature status is recorded with the artifact below.

At the initial audit handoff, no commits, pushes, publication, installer execution, or user-media processing had been performed. The subsequent request authorizes adding inline comments and committing and pushing these audited changes. The two remaining lifecycle findings above are still unresolved.

## Final local verification artifact

- Installer: `frontend/release/windows-build-verified/Expletive-Deleted-Setup-1.0.1-x64.exe`
- Size: 149,283,541 bytes.
- SHA-256: `64040c3d2e19127c9b9738c4202463824b008d7c88f101c16e1ca60f9379104f`
- Windows Authenticode status: **NotSigned**.
- Packaged executable: `frontend/release/windows-build-verified/win-unpacked/Expletive Deleted.exe`.
- This is an audit artifact, not a release-approved installer. The earlier `windows-build-audit` directory contains the superseded diagnostic build.
