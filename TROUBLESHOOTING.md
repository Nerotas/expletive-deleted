# Troubleshooting

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

In the desktop app, use **Finish local setup → Locate existing** to select `ffmpeg.exe`; the backend also locates and verifies the adjacent `ffprobe.exe`. Or choose **Get**, review the source and destination disclosure, and select **Continue**. The managed copy is stored below `%LOCALAPPDATA%\ExpletiveDeleted\dependencies\ffmpeg\` and does not modify the global `PATH`.

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

Use the repository virtual environment rather than a global Python installation:

```powershell
python setup.py
.\.venv\Scripts\python.exe diagnostics.py
```

The required packages are defined in `requirements.txt`.

## Whisper Uses CPU

CPU `int8` is the expected fallback when CUDA is unavailable, unsupported, or does not have enough memory for `large-v3`.

Inspect the selected profile with diagnostics. To deliberately force CPU for one shell:

```powershell
$env:CENSOR_WHISPER_DEVICE = 'cpu'
$env:CENSOR_WHISPER_COMPUTE_TYPE = 'int8'
```

Do not switch to a smaller model. The current censorship pipeline enforces `large-v3` for timestamp accuracy.

## Whisper Model or Cache Problems

Show cache locations and sizes:

```powershell
.\.venv\Scripts\python.exe manage_whisper_cache.py status
```

In the desktop app, choose **Get** only when you are ready to review and approve the model source, destination, and approximate size. Choose **Locate existing** to verify an existing faster-whisper cache instead. Processing never starts a model download implicitly.

Override the cache location when needed:

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

## Profanity Was Not Detected

Run report-only mode first:

```powershell
.\.venv\Scripts\python.exe batch_process.py --report-only
```

Review the transcript under the configured Transcripts directory, then classify the term from the desktop **Dictionary** page. The shipped files under `resources/` are factory defaults; the complete user-owned policy is stored atomically in `%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json`. Use the Dictionary page to import, export, or deliberately restore it.

If a surround transcript predates front-center transcription, the backend automatically rejects that cache and transcribes it again.

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
