# Windows lifecycle audit follow-up - 2026-09-16

Both remaining findings from [the Windows build audit](WINDOWS_BUILD_AUDIT_2026-09-16.md) are fixed. This closes the two identified code defects; it does not replace clean-machine installer and real-media release qualification.

## Safe shutdown and output publication

Electron closes the bridge input stream and allows up to 15 seconds for cancellation and cleanup before terminating an unresponsive bridge. Python cancels local jobs, downloads, and dependency setup, stops new submissions, and waits for workers. Download shutdown also terminates a silent subprocess that would otherwise keep its worker blocked on output.

The Windows bridge owns a non-inheritable Job Object handle configured to terminate its process tree when the handle closes. This contains descendants after normal exit, a bridge crash, or the forced fallback, including grandchildren. The implementation follows Microsoft's [Job Objects documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) and [nested job behavior](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs). No additional runtime dependency is introduced.

Every censored output is written to a unique staging filename. Before publication, the worker checks that the file is nonempty and FFprobe can read the required audio/video streams, then checks cancellation again. New outputs are published without overwriting a destination that appeared concurrently; replacement requires the existing overwrite authorization. Source archiving occurs only after verification and publication. This stream check is not a complete frame-by-frame decode or censorship accuracy guarantee.

Graceful cancellation removes staging output. Forced termination can leave a temporary `.partial` file, but it cannot publish that incomplete staged file under the finished filename. Originals remain intact before successful output publication and any explicitly configured archival step.

## Settings and active downloads

Settings changes now reject queued, downloading, and preparing downloads as well as local processing jobs. A shared lifecycle lock serializes settings replacement with submission, including YouTube metadata lookup. Downloads remain active until their optional transcription handoff completes, preventing a manager replacement during that callback. Completed downloads still permit settings changes.

## Validation

- Full repository Python suite: **266 tests passed**, including settings/submission races, active and queued job cancellation, output verification failure, destination collisions, download cancellation and callback state, setup cancellation, and real Windows child/grandchild containment.
- Frontend/Electron unit suite: **74 tests passed**, including graceful EOF cleanup and forced bridge termination.
- TypeScript check, production build, ESLint, and application version consistency passed.
- Standard native Electron smoke passed.
- New native Electron shutdown smoke passed for both cooperative and unresponsive workers. It drives the actual built Electron entrypoint, bridge protocol, service, and job manager using an offline synthetic encoder. Both cases preserve the source, avoid publishing incomplete output, and leave no encoder child running. The cooperative case also confirms cancellation cleanup.
- Both shutdown scenarios now run in Windows CI and the local release script.
- A fresh Windows x64 NSIS installer was built without publication. Packaged first-run smoke and private Python/pip executable verification passed. The package dependency and runtime file-hash audit passed before and after launch, with no forbidden processing components bundled or runtime bytecode mutations.

## Local verification artifact

- Installer: `frontend/release/windows-lifecycle-verified/Expletive-Deleted-Setup-1.0.1-x64.exe`.
- Size: 149,286,059 bytes.
- SHA-256: `b5e087d32f5172583de97f727fa0442c73b9f34b921418e970fd5357502f38e7`.
- Windows Authenticode status: **NotSigned**.
- Packaged executable: `frontend/release/windows-lifecycle-verified/win-unpacked/Expletive Deleted.exe`.
- This supersedes the original audit artifact and is a local verification build, not a release-approved installer. Generated artifacts remain outside Git.

## Coverage limits

The native shutdown fixture does not perform real FFmpeg encoding or large-v3 inference. The complete unit suite uses the repository interpreter; packaged smoke exercises private Python startup. A clean VM install/uninstall/upgrade, real model and GPU processing, live YouTube authentication, network/setup interruptions, antivirus behavior, and low-disk handling still need release qualification. No processing tools or models were downloaded for these regressions, and no user media was processed.

The user explicitly authorized fixing these two findings, adding explanatory comments, and committing and pushing the resulting work. No live site, release publication, or tag is part of this change.
