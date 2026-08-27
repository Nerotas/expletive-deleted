# Quick Start

Phase 5 and 6 provide a local Python application service and CLI. The Electron interface begins in Phase 7.

## First-time setup

Create the virtual environment and install the tested Python dependencies:

```powershell
python setup.py
```

Inspect prerequisites without downloading or installing anything:

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py status
.\.venv\Scripts\python.exe manage_dependencies.py plan --component whisper_model
```

The plan command displays the pinned source, revision, estimated size, command, and approval ID. Download the model only after reviewing that plan:

Profanity Censor requires Whisper `large-v3`. Smaller Whisper models do not provide reliable enough words or timestamps for this censorship workflow and are not supported. The dependency plan and runtime are deliberately pinned to `large-v3`; do not substitute a smaller model.

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py install --component whisper_model --approve PLAN_ID
```

Replace `PLAN_ID` with the exact value printed by the plan command. Then verify readiness:

```powershell
.\.venv\Scripts\python.exe backend_app.py capabilities
.\.venv\Scripts\python.exe diagnostics.py
```

## Configure processing

Initialize and inspect the persistent settings:

```powershell
.\.venv\Scripts\python.exe manage_settings.py init
.\.venv\Scripts\python.exe backend_app.py settings
```

Configure any Phase 6 options you want to test:

```powershell
.\.venv\Scripts\python.exe manage_settings.py set-options --mode report_only
.\.venv\Scripts\python.exe manage_settings.py set-options --mode censor --stereo-method drop_audio --padding-before-ms 150 --padding-after-ms 150 --surround-output preserve_5_1 --video-mode h264 --keep-original
```

Other supported values are `karaoke`, `downmix_stereo`, `preserve_source`, and processing devices `auto`, `cpu`, or `cuda`.

## Run locally

Put media in `%USERPROFILE%\Documents\Profanity Censor\Ready`, then inspect the Queue-equivalent library snapshot:

```powershell
.\.venv\Scripts\python.exe backend_app.py library
```

Run one file through the structured serial job service:

```powershell
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Profanity Censor\Ready\Movie.mkv" --mode report_only
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Profanity Censor\Ready\Movie.mkv" --mode censor
```

The result includes the final job record and structured stage, progress, detection, completion, or error events. Press `Ctrl+C` to request cancellation; partial output is removed and the source remains untouched.

To process every supported file in `Ready` serially through the compatibility batch command:

```powershell
.\.venv\Scripts\python.exe batch_process.py --list
.\.venv\Scripts\python.exe batch_process.py
```

Use `batch_process.py --list` to inspect files before processing. By default, censored media is written to `Finished`, transcripts are written to `Transcripts`, and the original remains in `Ready`. Use `--archive-original` to move originals to `Processed` only after verified success.

Inspect or change directories before processing:

```powershell
.\.venv\Scripts\python.exe manage_settings.py show
.\.venv\Scripts\python.exe manage_settings.py set-directories --input 'D:\Media\Ready' --create
```

Run the backend regression suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
