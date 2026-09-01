# Quick Start

Expletive Deleted has two ways to work:

- **Desktop application (recommended):** start Electron only. It starts the private Python processing bridge automatically and stops it when the app closes; use its setup screen to review, approve, install, and verify required components.
- **Backend and command line (advanced):** use the Python commands for development, automation, diagnostics, or a headless workflow.

Normal users should follow the desktop application workflow. Do not start `backend_app.py` or `scripts/desktop_bridge.py` in a second terminal when using the desktop app.

## Installed Windows application (recommended)

1. Install Python 3.9 or later from an approved Python distribution and ensure the `py` launcher or `python` command is available.
2. Run `Expletive-Deleted-Setup-<version>-x64.exe` and choose the installation directory.
3. Start **Expletive Deleted** from the Start menu or desktop shortcut.
4. Complete the explicit dependency plans shown by **Finish local setup**.

The installer contains the application and its first-party backend, but does not bundle or silently retrieve Python, FFmpeg, Python speech-recognition packages, or Whisper models. Uninstalling the application does not delete settings, downloaded runtime components, models, or user media beneath `%LOCALAPPDATA%\ExpletiveDeleted` and `%USERPROFILE%\Documents\Expletive Deleted`.

## Desktop source build (developers)

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

If anything is missing, the **Finish local setup** panel shows the affected component. Choose **Locate existing** to select and verify an installation already on the computer, or choose **Get** to review the exact third-party source, local destination, and download size before continuing. Canceling the disclosure does not start retrieval. After an approved operation, the backend verifies the component and refreshes System Ready status.

Approved FFmpeg binaries and Whisper models are stored beneath `%LOCALAPPDATA%\ExpletiveDeleted\`, outside the application package and user-media folders. The app does not modify the global Windows `PATH`. Runtime locations remain inspectable and changeable under **Settings → Runtime components**.

Whisper `large-v3` is required for reliable word-level censor timing. Smaller models are not supported for this workflow.

### Process media

1. In **Settings**, confirm the working folders and processing preferences. The default input folder is `%USERPROFILE%\Documents\Expletive Deleted\Ready`.
2. Add supported audio or video files to the configured Ready/Input folder.
3. Return to **Queue** and choose an action for one file:
   - **Transcribe only** creates and verifies a transcript without creating media output.
   - **Transcribe + Transcode** creates or validates the transcript first, then creates the censored output.
   - **Retranscribe** replaces an existing transcript with a newly generated, verified transcript while retaining any finished output.
   - **Retranscode** reuses a compatible transcript when one exists and safely replaces the finished censored output only after the new output succeeds.
   - **Archive** moves an original with a verified transcript or output to Processed while the queue is idle.
4. To process selected files serially, check the eligible Ready rows and choose **Queue transcript only** or **Queue transcribe + transcode**. Valid files remain queued if another selected file is rejected.
5. Use the status filters and sort control to inspect Ready, Queued, Active, Transcribed, or Finished files. The active row can be cancelled from its Actions group; waiting rows show their queue position and can be removed independently.
6. Review discovered potential profanity and update the local censor or ignore policy in the app when appropriate.

Jobs run one at a time in the displayed submission order. You can add files to Ready while another job is active; imported files are not queued automatically. Completed output is written to Finished/Output. Transcripts are reusable, and originals remain in Ready/Input unless explicitly archived.

Transcoding never begins from an in-memory transcription alone. The app must validate and persist the transcript, then re-open and verify the saved artifact. A valid transcript containing no words is accepted for media with no speech. If transcription or transcript persistence fails, no censored output is created and the source remains intact.

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
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Expletive Deleted\Ready\Movie.mkv" --mode report_only
.\.venv\Scripts\python.exe backend_app.py process "$env:USERPROFILE\Documents\Expletive Deleted\Ready\Movie.mkv" --mode censor
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
