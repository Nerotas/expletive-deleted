# Troubleshooting

## Closing During Processing or Downloading

Closing the desktop app requests cancellation and waits up to 15 seconds for cleanup. If a processing component does not respond, Windows terminates the backend and its child processes. A forced shutdown can leave a temporary `.partial` output file, but it is not listed as a finished copy. Original media is retained; reopen the app to retry. Existing completed output is replaced only after its replacement passes verification.

Settings saves are rejected while local jobs or YouTube downloads are active. Finish or cancel that work, then save the retained draft. This keeps download progress and cancellation attached to the current queue.

## Dictionary Is Busy or Needs Recovery

A busy dictionary means another desktop, CLI, or background operation holds the local transaction lock. Wait a moment and retry. The lock has a five-second wait limit and is released automatically if its process exits; do not delete `.policy.lock`.

An interrupted update may already have committed. Reload the dictionary before retrying: a valid `.policy-journal.json` is completed automatically before any snapshot is returned. Recovery keeps timestamps and entry sources and never uploads dictionary content.

If recovery fails, check access and free space in `%LOCALAPPDATA%\ExpletiveDeleted\dictionary`, then reopen the app. Keep the three JSON stores and journal intact. Invalid recovery data blocks reads and edits instead of replacing your dictionary with defaults. For persistent corruption, close desktop and CLI processes, preserve a private copy of the entire folder, and obtain application support to restore a known-good backup. Do not share dictionary or journal contents in public logs.

Opening the app again restores the existing window; it does not start another processing service. Do not run older application versions against the same dictionary: they do not honor transaction ownership or recovery.

## Start Here

Run the tracked readiness check from the repository root:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
```

It checks Python dependencies, runtime folders, FFmpeg, FFprobe, an executable H.264 encoder, the selected Whisper device, cache availability, and free disk space.

Run the backend regression suite separately:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## FFmpeg or FFprobe Is Missing

In the desktop app, use **Get ready → Locate existing** to select `ffmpeg.exe`; the backend also locates and verifies the adjacent `ffprobe.exe`. Or choose **Get Components**, review the source and destination disclosure, and select **Continue**. The managed copy is stored below `%LOCALAPPDATA%\ExpletiveDeleted\dependencies\ffmpeg\` and does not modify the global `PATH`.

Each saved FFmpeg or FFprobe override is honored independently during system checks and processing. YouTube imports require the selected executables to be in the same folder; use **Locate existing** to select a matching pair.

For advanced command-line use, install FFmpeg and rerun diagnostics.

```powershell
winget install --id Gyan.FFmpeg.Shared -e
```

You can also let the bootstrap invoke a supported package manager:

```powershell
python setup.py --install-system-dependencies
```

For a custom installation, set both executable paths for the current shell:

```powershell
$env:CENSOR_FFMPEG = 'C:\path\to\ffmpeg.exe'
$env:CENSOR_FFPROBE = 'C:\path\to\ffprobe.exe'
```

## A Python Dependency Is Missing

In an installed build, reopen **Get ready**, review the transcription-package plan, and approve installation into the private Python package directory under your local application data. A private Python startup failure is different: use the application's repair or reinstall guidance. No media is processed, uploaded, or changed while either issue is unresolved.

Use the repository virtual environment rather than a global Python installation:

```powershell
python setup.py
.\.venv\Scripts\python.exe diagnostics.py
```

The required packages are defined in `requirements.txt`. Readiness verifies both pinned versions and imports in a separate process using the processing interpreter and its search path. An import failure or a check that exceeds 30 seconds is reported as unavailable, even when package metadata is present.

## Whisper Uses CPU

CPU `int8` is the expected fallback when CUDA is unavailable, unsupported, or does not have enough memory for `large-v3`.

Inspect the selected profile with diagnostics. To deliberately force CPU for one shell:

```powershell
$env:CENSOR_WHISPER_DEVICE = 'cpu'
$env:CENSOR_WHISPER_COMPUTE_TYPE = 'int8'
```

Do not switch to a smaller model. The current censorship pipeline enforces `large-v3` for timestamp accuracy.

## Whisper Model or Cache Problems

In **Settings > Runtime components**, a blank **Whisper model location** uses the application-managed cache (normally `%LOCALAPPDATA%\ExpletiveDeleted\models\whisper`). System checks, setup, and processing use the same location. A saved custom location takes precedence; a missing custom cache does not silently fall back to another folder. Processing failures trigger a fresh system check.

If an older version reports **Processing ready** but fails with "Whisper model is not prepared," select the existing cache root in **Whisper model location**, save, and retry. Select the cache root rather than its nested snapshot folder. This reuses the existing download.

For advanced standalone cache-management commands, show cache locations and sizes:

```powershell
.\.venv\Scripts\python.exe manage_whisper_cache.py status
```

In the desktop app, choose **Get Components** only when you are ready to review and approve the model source, destination, and approximate size. Choose **Locate existing** to verify an existing faster-whisper cache instead. Processing never starts a model download implicitly.

Override the legacy standalone tools' cache location when needed (desktop and settings-driven batch processing use the saved setting above):

```powershell
$env:CENSOR_WHISPER_CACHE_DIR = 'D:\model-cache\whisper'
```

## No Files Appear in the Batch

Confirm the configured input directory and supported files:

```powershell
.\.venv\Scripts\python.exe batch_process.py --list
```

The CLI scans only the configured input directory. Inspect settings with `manage_settings.py show` and validate all paths with `manage_settings.py validate`. Supported extensions are `.avi`, `.flv`, `.m4a`, `.mkv`, `.mov`, `.mp3`, `.mp4`, `.wav`, `.webm`, and `.wmv`.

## Output Already Exists

The CLI skips an existing file in the configured output directory by default. Reprocess deliberately with:

```powershell
.\.venv\Scripts\python.exe batch_process.py --overwrite
```

The desktop application's final output-conflict policy remains an open product decision.

## A Job Is Waiting in Queue

Downloads, copies, transcription, and censoring have distinct queue states. Transcription and censoring share CPU, GPU, and media-storage resources, so only one heavy processing job runs at a time. A queued transcript or censor job starts after the current heavy job completes or is cancelled.

To censor a file, first create its transcript. Censor jobs use the persisted, verified transcript and fail without one; they do not transcribe the media again.

## Profanity Was Not Detected

Run report-only mode first:

```powershell
.\.venv\Scripts\python.exe batch_process.py --report-only
```

Review the transcript under the configured Transcripts directory, then classify the term from the desktop **Dictionary** page. The shipped files under `resources/` are factory defaults; live state is stored atomically in `%LOCALAPPDATA%\ExpletiveDeleted\dictionary\censored.json`, `exclusions.json`, and `discovered.json`. Use the Dictionary page to import, export, or deliberately restore it.

If **Play** reports that output cannot be verified, check FFprobe in Settings and that the completed copy remains in the configured output folder. Files moved elsewhere can be opened through Explorer. Dictionary exports accept ordinary `.json` files; if a selection expires or the destination changes during confirmation, select it again. The app retains a competing file instead of replacing it with the backup.

If a surround transcript predates front-center transcription, the backend rejects that cache and stops. Choose **Retranscribe** explicitly if you want a fresh transcript; existing transcript files are retained.

### Source identity needs review

Every processing job hashes the original's complete contents before accepting a transcript. A same-length replacement can therefore fail verification even if its filename and timestamp look unchanged. A failed check never triggers automatic retranscription. Startup and library polling show recorded artifact state without hashing the media.

Legacy transcripts and finished copies remain untouched and appear as **Needs review**. They are excluded from bulk processing. Keep them for a future preview-and-confirm mapping workflow, or choose **Retranscribe** for that individual source. Fresh transcripts use names such as `movie.mp4-transcript.json`; older `movie-transcript.json` files remain in place. Previous versions of a new-format transcript are retained under the transcript folder's `.history` directory.

Renamed or relocated files can reuse a uniquely matching, compatible fingerprinted transcript within the configured transcript root during a transcript job. Different matching transcripts require a decision. Unfingerprinted legacy files cannot be matched this way. Finished copies remain in their existing locations; they are not automatically renamed or migrated.

Keep the `.provenance.json` companion with each new finished copy. Playback verifies its source and output fingerprints. If publication was interrupted after media was saved but before its companion was written, the media and original remain intact, but verified playback is blocked. After reviewing the files, explicitly recensor with output replacement to publish a complete pair. Existing copies can still be opened manually through Explorer; doing so does not verify their relationship to an original.

## FFmpeg Processing Fails

Check the source streams:

```powershell
ffprobe -v error -show_streams -show_format input.mkv
```

Then rerun without hiding the CLI output. The backend prints the final FFmpeg error and retries a failed hardware video encoder with `libx264` when available.

To request software encoding explicitly:

```powershell
$env:CENSOR_VIDEO_ENCODER = 'libx264'
```

An override must be reported by the installed FFmpeg build and must successfully encode a test frame.

## Source Safety

The source is never modified in place and remains in the input directory by default. `--archive-original` moves it to the configured archive directory only after processing succeeds and the expected output exists. Existing archive destinations are never overwritten.

Failed, skipped, report-only, and non-archiving jobs retain their source.

## Still Failing

Capture these outputs when reporting an issue:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
.\.venv\Scripts\python.exe manage_settings.py validate
.\.venv\Scripts\python.exe -m unittest discover -s tests
ffmpeg -version
ffprobe -version
```

Include the failing command, the final error text, the media container and stream metadata, and whether the problem reproduces in report-only mode.

## A Selected Media Folder Changed

If the app reports that a selected folder changed, open Settings and choose the intended folder using its actual target path. The app remembers folder identity, so moving or retargeting a junction does not silently grant access to a different location. Your media is not moved by this check. Network/device paths and protected processing on non-Windows systems are currently unsupported.

If replacement reports a `.recovery` file, keep it: it contains the previous output. Close active processing before restoring it to a different, unused filename. Never overwrite a competing output to recover it. An interrupted replacement can also leave this hidden recovery file; it is not an incomplete media file to discard.

## Managed Download Destinations

Approved yt-dlp and Deno installs write to the managed destination shown in the setup plan and verify that copy. The advanced `CENSOR_YTDLP` and `CENSOR_DENO` environment variables select existing executables for use; they do not redirect installation or overwrite those external executables.

## Component settings need review

Setup can finish retrieving a component while a newer path or preference is saved. **Review component settings** shows the current and verified paths. Choose **Keep current** or **Use verified**, then **Apply choices**. This verifies existing files and saves settings; it does not reinstall or repeat a completed download. Keeping a manual path does not guarantee that path is ready.

If a media job or download is active, finish or cancel it before applying choices again. If saving fails, fix the reported permissions or disk problem and retry the same settings review. Cancel leaves verified files intact and retains the pending review in the current app session; use the top status button to reopen it. After restarting the app, **Locate existing** can verify and select the retained files.

Settings and the setup wizard also pause if the same field changed elsewhere. Choose the current value or your edit; Cancel preserves the draft and current step. A further change may require another choice.

In **Settings changed elsewhere**, every listed field needs an explicit **Keep current** or **Use my edit** choice. Press Escape or **Cancel** to return to the draft without saving. If saving fails, correct the reported problem and retry; your edits remain. **Discard** on normal Settings restores the latest saved values. Replaying onboarding starts from saved settings and leaves unsaved normal Settings edits available for a separate save or discard.

Advanced: CLI settings writers report `settings_busy` while the desktop owns the profile. Close the desktop before running `manage_settings.py init`, `set-options`, or `set-directories`. Read-only settings commands and dictionary CLI transactions remain available. Settings use local thread/process locks; older app versions do not honor these locks, so do not run old and new versions against one profile concurrently.

### Setup reconnecting or outcome unknown

A lost response does not prove that installation failed or finished. The app shows elapsed reconnection time for up to 30 seconds. If the local service has exited, it offers recovery immediately. **Retry connection** only checks existing status, including a start or cancellation whose acknowledgement was lost. It never resends installation or cancellation commands.

Use **Restart app** if the service stopped or cannot respond. Restart can stop unfinished work but retains completed component files. Once the app reopens, check components, locate an existing component if needed, and review a fresh plan before approving remaining setup. A settings conflict still uses **Keep current** / **Use verified**, without reinstalling.
