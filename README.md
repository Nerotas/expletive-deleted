# Profanity Censor

Profanity Censor transcribes audio and video locally with faster-whisper, identifies configured profanity from word-level timestamps, and censors those intervals with FFmpeg. The Phase 7 Electron desktop interface controls the local Python application service; this is not a browser-hosted application.

Windows is the current application target. The processing engine remains portable, but macOS and Linux packaging are future work.

See [QUICKSTART.md](QUICKSTART.md) for the condensed command sequence and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common setup failures.

## Workflow

1. Put source media in the configured Ready/Input directory.
2. Choose **Transcribe only** or **Transcribe + Transcode** for one file, or select Ready files for the serial queue.
3. Whisper transcribes the input and atomically stores a validated reusable transcript in the configured Transcripts directory.
4. For combined jobs, the saved transcript is re-opened and verified before FFmpeg can create the censored result in Finished/Output.
5. The original remains in place unless archival is explicitly requested after a verified transcript or output exists.

Outputs are never overwritten silently. Application-service jobs fail clearly on a conflict; compatibility batch runs skip the file unless overwrite is explicitly enabled.

## Repository Layout

The working Python implementation now lives under `backend/`:

```text
backend/censor/engine.py       transcription, detection, and FFmpeg censoring
backend/jobs/                  serial job manager, events, records, and batch compatibility
backend/runtime/environment.py dependency, hardware, cache, and encoder discovery
backend/runtime/paths.py       runtime directory ownership
backend/settings/              validated models, persistence, and path checks
backend/service/               settings, library, capabilities, and application boundary
resources/                     curated profanity policy files
scripts/                       bootstrap, diagnostics, and maintenance commands
tests/                         backend regression tests
backend_app.py                 local Phase 5+6 application-service entry point
```

The root Python commands remain as compatibility entry points. New backend code should import package modules directly.

## Requirements

- Python 3.9 or later
- FFmpeg and FFprobe
- Disk space for source media, output media, and Whisper model downloads

The repository bootstrap installs Python packages in a local `.venv`. FFmpeg and the Whisper model follow the reviewed dependency-plan workflow described below.

User media and transcripts default to `Documents\Profanity Censor`. Internal settings use the operating system's application-data location in an automatically created `settings.ini`. Runtime assets explicitly retrieved through the desktop setup flow use `%LOCALAPPDATA%\ExpletiveDeleted\dependencies` and `%LOCALAPPDATA%\ExpletiveDeleted\models`; they are not written into the packaged application or user-media folders.

## Prepare the Application

From the repository root:

```powershell
python setup.py
```

The command creates `.venv`, persists validated settings, creates the four configured working directories, and installs dependencies from `requirements.txt` into the virtual environment.

Inspect application prerequisites without installing or downloading anything:

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py status
```

Missing components are installed only through an inspectable plan. For example, review the pinned `large-v3` model source, revision, estimated download size, and command:

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py plan --component whisper_model
```

After reviewing the plan, replace `PLAN_ID` with the exact approval ID it prints:

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py install --component whisper_model --approve PLAN_ID
```

Use the same `plan` then `install --approve` flow with `--component ffmpeg` or `--component python` when either is reported missing. Nothing is retrieved silently.

Windows defaults:

```text
%USERPROFILE%\Documents\Profanity Censor\Ready
%USERPROFILE%\Documents\Profanity Censor\Finished
%USERPROFILE%\Documents\Profanity Censor\Processed
%USERPROFILE%\Documents\Profanity Censor\Transcripts
```

Settings are stored at `%LOCALAPPDATA%\ProfanityCensor\settings.ini` by default. The generated, machine-specific file is ignored by Git; [`config.example.ini`](config.example.ini) documents its schema.

The advanced CLI setup retains its repository-local `whisper-cache/` default and prints the active path and size. The desktop setup flow instead uses its per-user managed model directory unless the user selects another verified cache in Settings.

When FFmpeg is missing, the approved dependency plan installs the pinned cross-platform `static-ffmpeg` runtime manager and then downloads its matching `ffmpeg` and `ffprobe` binaries. The app records their paths locally; it does not require WinGet or modify the system `PATH`.

## Verify Readiness

Run this non-destructive diagnostic check:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
.\.venv\Scripts\python.exe backend_app.py capabilities
```

On macOS or Linux:

```bash
.venv/bin/python diagnostics.py
```

A ready machine reports FFmpeg, FFprobe, Python dependencies, and `model_large_v3` as available. Diagnostics also verifies working folders, the selected H.264 encoder, and disk space.

## Configure the Application

Inspect the effective settings:

```powershell
.\.venv\Scripts\python.exe backend_app.py settings
```

Configure all processing preferences through the Settings page or validated commands; the same changes are saved to `settings.ini`:

```powershell
# Safe first pass: transcribe and report without creating media output.
.\.venv\Scripts\python.exe manage_settings.py set-options --mode report_only

# Example censor configuration.
.\.venv\Scripts\python.exe manage_settings.py set-options --mode censor --device auto --stereo-method drop_audio --padding-before-ms 150 --padding-after-ms 150 --surround-output preserve_5_1 --video-mode h264 --keep-original
```

Supported alternatives include `karaoke`, `downmix_stereo`, `preserve_source`, and devices `cpu` or `cuda`. Archiving is off by default; `--archive-after-success` moves a source to `Processed` only after verified success.

Change any working directory independently when needed:

```powershell
.\.venv\Scripts\python.exe manage_settings.py set-directories --input 'D:\Media\Ready' --output 'D:\Media\Finished' --create
```

## Use the Local Application

Launch the native desktop application from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Vite is used only as Electron's renderer build and hot-reload tool. Normal users interact with the Electron window, not a browser URL.

The desktop Queue provides explicit per-file **Transcribe only**, **Transcribe + Transcode**, and **Archive** actions. Checkboxes queue an exact selection in the displayed sort order, and the backend processes one job at a time. Filters expose Ready, Queued, Active, Transcribed, and Finished rows; waiting jobs display `#1`, `#2`, and so on and can be removed independently. Files may be imported while processing continues, but imports remain Ready until the user queues them.

Every censor job has a hard transcript gate. A compatible cache may be reused; otherwise Whisper must produce a transcript whose structure, profile, audio source, and word timestamps validate. New transcripts are written atomically and verified from disk before profanity detection or FFmpeg processing begins. Empty word lists are valid for media with no speech.

Place a supported file in the configured `Ready` directory and inspect the Queue-equivalent library snapshot:

```powershell
.\.venv\Scripts\python.exe backend_app.py library
```

Start with report-only processing:

```powershell
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Profanity Censor\Ready\Movie.mkv" --mode report_only
```

After reviewing the transcript and detections, create censored output:

```powershell
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Profanity Censor\Ready\Movie.mkv" --mode censor
```

The command returns the final job record and structured stage, progress, detection, completion, or error events. Jobs run serially. Press `Ctrl+C` to request cancellation; incomplete output is removed and the source remains untouched.

Artifacts are written to:

```text
Ready        source media, retained by default
Transcripts  reusable transcript and detection data
Finished     completed censored media
Processed    originals archived only after successful output when enabled
```

If the expected output already exists, the application-service job fails clearly instead of overwriting it. The compatibility batch command skips it unless `--overwrite` is explicitly supplied.

## Compatibility Batch Processing

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

The report lists words detected by the broader `better-profanity` vocabulary that are not in your effective policy, with occurrence counts and timestamps. Classify reviewed words from the desktop **Dictionary** page. User decisions are stored locally in `%LOCALAPPDATA%\ProfanityCensor\policy.json` and are applied to future desktop and CLI runs.

The default censor run combines the shipped [censor defaults](resources/profanity_censor_words.txt), shipped [exclusions](resources/profanity_exclusions.txt), and the local user-policy overlay. It skips inputs with an existing output. Use these deliberate opt-in controls when needed:

```powershell
# Replace an existing censored output for files still in ready/.
.\.venv\Scripts\python.exe batch_process.py --overwrite

# Censor and report words found only in better-profanity's broad vocabulary,
# unless they are excluded by the effective policy.
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

Recognized `5.1`, `5.1(side)`, `7.1`, `7.1(wide)`, and `7.1(wide-side)` sources are handled automatically, regardless of stereo censor method. Whisper transcribes only the discrete front-center channel. During each flagged interval, FFmpeg drops that channel while preserving the other surround channels. The configured output either preserves surround or downmixes the censored result to stereo; censorship always occurs before downmixing. Existing surround transcript caches created from a full mix are regenerated once and tagged for safe reuse.

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

Application settings use a versioned `settings.ini` schema and atomic writes. Inspect, initialize, validate, or update working directories without a frontend:

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

The application service and batch workflow apply processing mode, device, stereo censor method, before/after padding, surround output, video output, and source archival settings. Batch CLI flags such as `--report-only`, `--censor-media`, `--censor-method`, `--archive-original`, and `--keep-original` override their matching settings for one run.

The workflow does not use `better-profanity`'s broad built-in dictionary for normal censoring. The text files under `resources/` are immutable product defaults. User additions, exclusions, moves, and removals belong in the desktop **Dictionary**, which writes a versioned override document to `%LOCALAPPDATA%\ProfanityCensor\policy.json`. Writes are staged, verified, and atomically replaced.

The effective policy is recalculated whenever a job starts. New defaults shipped in an upgrade appear automatically, while explicit user removals remain removed. A word can be classified as censored, excluded, or removed, but never censored and excluded simultaneously.

For an advanced workstation deployment, `CensorWordsFile` and `ExclusionsFile` under the legacy project `[Profanity]` configuration can replace the shipped baseline. To inject a different baseline for one run:

```powershell
$env:CENSOR_CENSOR_WORDS_FILE = 'D:\media-policies\strict-censor-words.txt'
.\.venv\Scripts\python.exe batch_process.py
```

To inject a different exclusions baseline, use `CENSOR_EXCLUSIONS_FILE` the same way. `CENSOR_POLICY_FILE` can select a different user-policy overlay. Each job reports the effective policy counts it loaded without logging transcript content.

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

- Processing never downloads `large-v3` implicitly. Review and approve its dependency plan before the first transcription.
- Review censored output before distributing it. Whisper timestamps and profanity detection can require tuning for difficult audio.
- Repository-relative `ready/`, `finished/`, `processed/`, and `transcripts/` remain ignored for `CENSOR_PROJECT_ROOT` compatibility.
