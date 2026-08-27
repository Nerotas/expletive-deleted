# Quick Start

Profanity Censor has two ways to work:

- **Desktop application (recommended):** start Electron only. It starts the private Python processing bridge automatically and stops it when the app closes; use its setup screen to review, approve, install, and verify required components.
- **Backend and command line (advanced):** use the Python commands for development, automation, diagnostics, or a headless workflow.

Normal users should follow the desktop application workflow. Do not start `backend_app.py` or `scripts/desktop_bridge.py` in a second terminal when using the desktop app.

## Desktop application (recommended)

The desktop source build requires Node.js 22.12 or later. Confirm it before installing frontend packages:

```powershell
node --version
```

For a source checkout, create the local Python environment once from the repository root:

```powershell
python setup.py
```

Then start the desktop application:

```powershell
cd frontend
npm install
npm run dev
```

`npm run dev` opens the native Electron window and launches the local Python bridge as its child process. Vite is only used to build and hot-reload the Electron renderer; this is not a browser-hosted application. You start one command, not two.

### Complete first-run setup in the app

The first launch checks the local system for:

- FFmpeg and FFprobe
- Python speech-recognition dependencies
- Whisper `large-v3`

If anything is missing, the **Finish local setup** panel shows the affected component. Select **Install** and the app installs and verifies it. The underlying dependency plan remains internal so the same tested, pinned components are used by the desktop app and CLI.

Whisper `large-v3` is required for reliable word-level censor timing. Smaller models are not supported for this workflow.

### Process media

1. In **Settings**, confirm the working folders and processing preferences. The default input folder is `%USERPROFILE%\Documents\Profanity Censor\Ready`.
2. Add supported audio or video files to the configured Ready/Input folder.
3. Return to **Queue**, refresh if needed, then choose **Start batch**.
4. Review discovered potential profanity and update the local censor or ignore policy in the app when appropriate.

Completed output is written to Finished/Output. Transcripts are reusable, and originals remain in Ready/Input unless **Archive original after success** is enabled.

## Backend and command line (advanced)

Use this workflow only when developing, automating, diagnosing a machine, or operating without the desktop UI.

### Create the local Python environment

From the repository root:

```powershell
python setup.py
```

This creates `.venv`, installs the Python requirements, persists validated settings, and creates the working directories. It does not silently download the Whisper model or install FFmpeg.

### Inspect or install backend dependencies

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py status
.\.venv\Scripts\python.exe manage_dependencies.py plan --component ffmpeg
.\.venv\Scripts\python.exe manage_dependencies.py plan --component whisper_model
```

Review the exact plan first. To perform an approved installation, replace `PLAN_ID` with the ID returned by `plan`:

```powershell
.\.venv\Scripts\python.exe manage_dependencies.py install --component ffmpeg --approve PLAN_ID
.\.venv\Scripts\python.exe manage_dependencies.py install --component whisper_model --approve PLAN_ID
```

The FFmpeg plan installs the pinned cross-platform `static-ffmpeg` runtime manager, then downloads its matching `ffmpeg` and `ffprobe` binaries only after approval. It does not require WinGet or modify the system `PATH`.

### Diagnose and run backend jobs

```powershell
.\.venv\Scripts\python.exe diagnostics.py
.\.venv\Scripts\python.exe backend_app.py capabilities
.\.venv\Scripts\python.exe backend_app.py library
```

Run one file through the application service:

```powershell
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Profanity Censor\Ready\Movie.mkv" --mode report_only
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Profanity Censor\Ready\Movie.mkv" --mode censor
```

For compatibility batch processing:

```powershell
.\.venv\Scripts\python.exe batch_process.py --list
.\.venv\Scripts\python.exe batch_process.py
```

Use the settings CLI only for automation or diagnostics:

```powershell
.\.venv\Scripts\python.exe manage_settings.py show
.\.venv\Scripts\python.exe manage_settings.py set-directories --input 'D:\Media\Ready' --create
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
