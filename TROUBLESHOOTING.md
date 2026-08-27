# Troubleshooting

## Start Here

Run the tracked readiness check from the repository root:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
```

It checks Python dependencies, runtime folders, FFmpeg, FFprobe, an executable H.264 encoder, the selected Whisper device, cache availability, and free disk space.

Run the backend regression suite separately:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_runtime tests.test_diagnostics
```

## FFmpeg or FFprobe Is Missing

Install FFmpeg, open a new terminal, and rerun diagnostics.

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

The current CLI retrieves the model through faster-whisper on the first transcription when it is not cached. A future desktop setup flow will ask before downloading it.

Override the cache location when needed:

```powershell
$env:CENSOR_WHISPER_CACHE_DIR = 'D:\model-cache\whisper'
```

## No Files Appear in the Batch

Confirm the active runtime root and supported files:

```powershell
.\.venv\Scripts\python.exe batch_process.py --list
```

The CLI scans only `ready/` under the active `CENSOR_PROJECT_ROOT`. Supported extensions are `.avi`, `.flv`, `.m4a`, `.mkv`, `.mov`, `.mp3`, `.mp4`, `.wav`, `.webm`, and `.wmv`.

## Output Already Exists

The CLI skips an existing file in `finished/` by default. Reprocess deliberately with:

```powershell
.\.venv\Scripts\python.exe batch_process.py --overwrite
```

The desktop application's final output-conflict policy remains an open product decision.

## Profanity Was Not Detected

Run report-only mode first:

```powershell
.\.venv\Scripts\python.exe batch_process.py --report-only
```

Review the transcript under `transcripts/`. Add approved terms to `resources/profanity_censor_words.txt`; add false positives to `resources/profanity_exclusions.txt`.

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

The source is never modified in place. The current batch CLI moves a source from `ready/` to `processed/` only after processing succeeds and the expected output exists.

Failed, skipped, or report-only jobs remain in `ready/`.

## Still Failing

Capture these outputs when reporting an issue:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
.\.venv\Scripts\python.exe -m unittest tests.test_runtime tests.test_diagnostics
ffmpeg -version
ffprobe -version
```

Include the failing command, the final error text, the media container and stream metadata, and whether the problem reproduces in report-only mode.
