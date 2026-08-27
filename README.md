# Profanity Censor

Batch-process audio and video with faster-whisper, identify profane words from word-level timestamps, and mute those audio intervals with FFmpeg. The workflow is designed to be portable across Windows, macOS, Linux, and WSL, with hardware encoding selected when available.

## Workflow

1. Put source media in the configured Ready/Input directory.
2. Run the batch command.
3. Whisper transcribes the input and stores a reusable transcript in the configured Transcripts directory.
4. FFmpeg mutes detected profanity and writes the censored result to the configured Finished/Output directory.
5. The original remains in place unless archive-after-success is explicitly enabled.

Outputs are skipped when a file with the expected censored name already exists.

## Repository Layout

The working Python implementation now lives under `backend/`:

```text
backend/censor/engine.py       transcription, detection, and FFmpeg censoring
backend/jobs/batch.py          serial folder-batch orchestration
backend/runtime/environment.py dependency, hardware, cache, and encoder discovery
backend/runtime/paths.py       runtime directory ownership
backend/settings/              validated models, persistence, and path checks
resources/                     curated profanity policy files
scripts/                       bootstrap, diagnostics, and maintenance commands
tests/                         backend regression tests
```

The root Python commands remain as compatibility entry points. New backend code should import package modules directly.

## Requirements

- Python 3.9 or later
- FFmpeg and FFprobe
- Disk space for source media, output media, and Whisper model downloads

The repository bootstrap installs Python packages in a local `.venv`. It can optionally install FFmpeg through a detected package manager.

User media and transcripts default to `Documents\Profanity Censor`. Internal settings use the operating system's application-data location; the current development model cache remains under the repository unless overridden.

## Setup

From the repository root:

```powershell
python setup.py --install-system-dependencies
```

The command creates `.venv`, persists validated settings, creates the four configured working directories, and installs dependencies from `requirements.txt` into the virtual environment.

Windows defaults:

```text
%USERPROFILE%\Documents\Profanity Censor\Ready
%USERPROFILE%\Documents\Profanity Censor\Finished
%USERPROFILE%\Documents\Profanity Censor\Processed
%USERPROFILE%\Documents\Profanity Censor\Transcripts
```

Settings are stored at `%LOCALAPPDATA%\ProfanityCensor\settings\settings.json` by default.

Setup also creates a repository-local Whisper cache at `whisper-cache/` by default and prints both the active cache path and current cache size. If Whisper models were previously downloaded to the user cache outside the repo, setup points you to the cache migration helper.

When FFmpeg is missing, `--install-system-dependencies` uses a supported package manager when present:

```powershell
# Windows: winget, including the WindowsApps alias when it is not on PATH
winget install --id Gyan.FFmpeg.Shared -e

# Windows: Chocolatey fallback
choco install ffmpeg -y

# macOS: Homebrew
brew install ffmpeg

# Ubuntu/Debian: run manually because sudo is not automated
sudo apt install ffmpeg
```

On Windows, start a new PowerShell session after an FFmpeg install if commands are not yet available from `PATH`. The runtime also recognizes winget-managed FFmpeg aliases directly.

## Verify Readiness

Run this non-destructive diagnostic check:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
```

On macOS or Linux:

```bash
.venv/bin/python diagnostics.py
```

A successful check ends with:

```text
Ready. Place media in the configured input directory and run: python batch_process.py
```

Diagnostics verifies the working folders, Python packages, FFmpeg/FFprobe, selected H.264 encoder, and available disk space.

## Batch Processing

Place supported media in the configured input directory, then run:

```powershell
.\.venv\Scripts\python.exe batch_process.py
```

The workflow always uses Whisper `large-v3` for the word-level timing accuracy required to mute only profane audio. Smaller models are not supported for censorship processing. This is enforced in the batch CLI, PowerShell wrapper, direct processor CLI, runtime validation, and model-cache management.

List files without changing anything:

```powershell
.\.venv\Scripts\python.exe batch_process.py --list
```

Review potentially profane words without creating output files or moving source media:

```powershell
.\.venv\Scripts\python.exe batch_process.py --report-only
```

The report lists words detected by the broader `better-profanity` vocabulary that are not in your curated censor list or exclusions file, with occurrence counts and timestamps. Add reviewed words to [resources/profanity_censor_words.txt](resources/profanity_censor_words.txt) to censor them in future runs, or [resources/profanity_exclusions.txt](resources/profanity_exclusions.txt) to permanently ignore them.

The default censor run uses [resources/profanity_censor_words.txt](resources/profanity_censor_words.txt) as the source of truth and skips inputs with an existing output. Use these deliberate opt-in controls when needed:

```powershell
# Replace an existing censored output for files still in ready/.
.\.venv\Scripts\python.exe batch_process.py --overwrite

# Censor and report words found only in better-profanity's broad vocabulary,
# unless they are present in resources/profanity_exclusions.txt.
.\.venv\Scripts\python.exe batch_process.py --include-undiscovered

# Combine both for a full reprocess using the broad vocabulary.
.\.venv\Scripts\python.exe batch_process.py --overwrite --include-undiscovered

# Archive originals only after verified successful output.
.\.venv\Scripts\python.exe batch_process.py --archive-original
```

Use `--report-only` first to review these undiscovered words before enabling broad-vocabulary censoring.

### Censor Method

For mono and stereo sources, the workflow silences audio during each profane interval by default (`--censor-method mute`). An alternative **karaoke** method is also available for stereo sources:

```powershell
.\.venv\Scripts\python.exe batch_process.py --censor-method karaoke
```

Instead of a hard silence, the karaoke method subtracts the right channel from the left (and vice-versa) during each flagged interval. Audio that is panned equally in both channels - typically centre-panned dialogue and vocals - cancels out. The stereo difference signal - music, ambient sound, and off-centre effects - is preserved, so the gap is less jarring than a clean mute.

The technique relies on dialogue being centre-panned. Its effectiveness varies by mix: some audio will be attenuated rather than fully removed. If the source audio is mono, the method has no effect and the workflow automatically falls back to mute with a warning.

Recognized `5.1`, `5.1(side)`, `7.1`, `7.1(wide)`, and `7.1(wide-side)` sources are handled automatically, regardless of `--censor-method`. Whisper transcribes only the discrete front-center channel. During each flagged interval, FFmpeg drops that channel while preserving the other surround channels, then downmixes the result to two-channel stereo during the final transcode. Existing surround transcript caches created from a full mix are regenerated once and tagged for safe reuse.

Windows also has a convenience wrapper:

```powershell
.\convert-profanity-censor.ps1 -Model large
.\convert-profanity-censor.ps1 -List
.\convert-profanity-censor.ps1 -ReportOnly
.\convert-profanity-censor.ps1 -Overwrite -IncludeUndiscovered
```

Supported input formats are `.avi`, `.flv`, `.m4a`, `.mkv`, `.mov`, `.mp3`, `.mp4`, `.wav`, `.webm`, and `.wmv`. Audio-only inputs produce `.mp3`; video inputs produce `.mkv`.

## Single-File Processing

For an explicit input/output path, call the processor directly:

```powershell
.\.venv\Scripts\python.exe censor_profanity.py input.mkv output.mkv large transcripts
```

Arguments are:

```text
censor_profanity.py INPUT OUTPUT [large] [TRANSCRIPTS_DIR]
```

Pass `--censor-method karaoke` to use centre-channel cancellation instead of hard muting:

```powershell
.\.venv\Scripts\python.exe censor_profanity.py input.mkv output.mkv --censor-method karaoke
```

## Acceleration

The runtime detects FFmpeg encoders and chooses the first available option in this order:

1. NVIDIA NVENC: `h264_nvenc`
2. Intel Quick Sync Video: `h264_qsv`
3. Apple VideoToolbox: `h264_videotoolbox`
4. CPU fallback: `libx264`

If a hardware encoder is detected but fails while processing, the workflow retries with `libx264` when it is available. WSL works with FFmpeg but does not assume GPU access; native Windows is recommended for NVIDIA acceleration.

Whisper selects a profile automatically on each machine through its CTranslate2 backend. It queries CUDA availability, supported compute types, and NVIDIA GPU memory before each run. CPU-only systems use `int8`; supported GPUs use the best available compute type, such as `float16` or `int8_float32`. Whisper `large-v3` requires at least 8 GB of GPU memory. When the GPU is insufficient, the workflow safely uses CPU `int8` rather than lowering the model quality.

`setup.py` installs dependencies and prints the `large-v3` profile detected through the new virtual environment. The persisted device preference is evaluated against each machine at batch time.

After each completed transcription, the workflow records its throughput in a local ignored `.whisper-timing.json` file. Future preflight estimates use the median of the five most recent matching `large-v3` hardware-profile runs for that workstation. Until a matching run completes, the estimate is explicitly labeled as conservative; the live `[TX]` ETA uses the current file's observed progress.

Override executable discovery or select a specific encoder with environment variables:

```powershell
$env:CENSOR_FFMPEG = 'C:\path\to\ffmpeg.exe'
$env:CENSOR_FFPROBE = 'C:\path\to\ffprobe.exe'
$env:CENSOR_VIDEO_ENCODER = 'libx264'
$env:CENSOR_WHISPER_DEVICE = 'cpu' # Use cpu, cuda, or auto.
$env:CENSOR_WHISPER_COMPUTE_TYPE = 'int8' # Or a supported CUDA type.
```

An encoder override must be listed by `ffmpeg -encoders` or processing fails clearly.

## Configuration

Application settings use a versioned JSON schema and atomic writes. Inspect, initialize, validate, or update working directories without a frontend:

```powershell
.\.venv\Scripts\python.exe manage_settings.py show
.\.venv\Scripts\python.exe manage_settings.py init
.\.venv\Scripts\python.exe manage_settings.py validate
.\.venv\Scripts\python.exe manage_settings.py set-directories --input 'D:\Media\Ready' --create
```

Each directory can be set independently with `--input`, `--output`, `--archive`, and `--transcripts`. Duplicate, relative, malformed, inaccessible, and non-directory paths are rejected.

`CENSOR_PROJECT_ROOT` remains a compatibility override for the four legacy repository-style folders. It overrides only directories for the current process; other persisted settings remain active:

```powershell
$env:CENSOR_PROJECT_ROOT = 'D:\media-censor-workflow'
.\.venv\Scripts\python.exe batch_process.py --list
```

Whisper model downloads default to the project-relative `whisper-cache/` folder. Override it only when you intentionally want models stored outside the repo:

```powershell
$env:CENSOR_WHISPER_CACHE_DIR = 'D:\model-cache\whisper'
.\.venv\Scripts\python.exe setup.py
```

Under `[Whisper]`, `Device = auto` and `ComputeType = auto` are the portable defaults. They are evaluated on each machine. `CENSOR_WHISPER_DEVICE` and `CENSOR_WHISPER_COMPUTE_TYPE` take precedence for a single run or a locally managed workstation policy.

Processing defaults currently applied by batch are mode, device, stereo censor method, and source archival. CLI flags such as `--report-only`, `--censor-media`, `--censor-method`, `--archive-original`, and `--keep-original` override them for one run.

The workflow uses the curated inclusion list in [resources/profanity_censor_words.txt](resources/profanity_censor_words.txt), not `better-profanity`'s much broader built-in dictionary. Add only words that should produce censored audio, one per line. Blank lines and text after `#` are ignored. The optional `CensorWordsFile` setting under `[Profanity]` can replace the default.

Use [resources/profanity_exclusions.txt](resources/profanity_exclusions.txt) only as a final override for a configured word that should not be censored. To inject a different source list for one run without modifying the project configuration:

```powershell
$env:CENSOR_CENSOR_WORDS_FILE = 'D:\media-policies\strict-censor-words.txt'
.\.venv\Scripts\python.exe batch_process.py
```

To inject a different exclusions file, use `CENSOR_EXCLUSIONS_FILE` the same way. The batch process passes both settings to every file it processes. Each run prints the source and exclusions files it loaded, with their entry counts.

To inspect, migrate, or clean Whisper model caches:

```powershell
.\.venv\Scripts\python.exe manage_whisper_cache.py status
.\.venv\Scripts\python.exe manage_whisper_cache.py migrate --clean-external
.\.venv\Scripts\python.exe manage_whisper_cache.py prune-unused
```

## Tests

Run the complete backend test suite without processing real media:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Notes

- The first transcription downloads `large-v3` when it is not already cached.
- Review censored output before distributing it. Whisper timestamps and profanity detection can require tuning for difficult audio.
- Repository-relative `ready/`, `finished/`, `processed/`, and `transcripts/` remain ignored for `CENSOR_PROJECT_ROOT` compatibility.
