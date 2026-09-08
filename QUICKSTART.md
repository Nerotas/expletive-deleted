# Quick Start

Expletive Deleted has two ways to work:

- **Desktop application (recommended):** start Electron only. It starts the private Python processing bridge automatically and stops it when the app closes; use its setup screen to review, approve, install, and verify required components.
- **Backend and command line (advanced):** use the Python commands for development, automation, diagnostics, or a headless workflow.

Normal users should follow the desktop application workflow. Do not start `backend_app.py` or `scripts/desktop_bridge.py` in a second terminal when using the desktop app.

## Installed Windows application (recommended)

1. Run `Expletive-Deleted-Setup-<version>-x64.exe` and choose the installation directory.
2. Start **Expletive Deleted** from the Start menu or desktop shortcut.
3. If Python is missing, the first screen explains why it is needed and offers **Get Python**, which opens the official download page. After Python 3.9 or later is installed, return to the app and choose **Try again**.
4. Follow the in-app walkthrough to check local components, choose initial settings, and optionally try a first file.

The installer contains the application and its first-party backend, but does not bundle or silently retrieve Python, the external `ffmpeg.exe`/`ffprobe.exe` processing runtime, Python speech-recognition packages, or Whisper models. Electron's required Chromium codec `ffmpeg.dll` is part of the desktop framework, cannot process jobs, and does not count as an installed FFmpeg dependency. Uninstalling the application does not delete settings, downloaded runtime components, models, or user media beneath `%LOCALAPPDATA%\ExpletiveDeleted` and `%USERPROFILE%\Documents\Expletive Deleted`.

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

The walkthrough has six sections: Welcome, Get ready, Your settings, Add a file, Process safely, and Finish. Each section is implemented under `frontend/src/features/onboarding/` so developers can change and test it without editing the rest of the walkthrough. The app saves progress when you choose **Save & Continue**, so an unfinished first run resumes at the last saved section. Reopening a completed walkthrough starts at Welcome and leaves its completed status intact until you finish again.

If the private local processing service cannot start, the Electron window explains that Python or its required packages need attention and links to the official Python download page. No media is uploaded or changed while the service is unavailable.

The first launch checks the local system for:

- FFmpeg and FFprobe
- Python speech-recognition dependencies
- Whisper `large-v3`

If two or more required components are missing, choose **Get required components** to prepare one combined plan. It includes FFmpeg/FFprobe, Python speech-recognition packages, and the Whisper model, but never optional yt-dlp. You can also choose **Locate existing** to verify an installation already on the computer, or **Get Components** for one item. The review shows each third-party source, local destination, and download size before continuing. Canceling the disclosure does not start retrieval. After an approved operation, the backend verifies the component and refreshes System Ready status.

Approved FFmpeg binaries and Whisper models are stored beneath `%LOCALAPPDATA%\ExpletiveDeleted\`, outside the application package and user-media folders. The app does not modify the global Windows `PATH`. Runtime locations remain inspectable and changeable under **Settings → Runtime components**.

Whisper `large-v3` is required for reliable word-level censor timing. Smaller models are not supported for this workflow.

### Process media

1. In **Your settings** during first-run setup, or later in **Settings**, confirm the working folders and processing preferences. **Automatically create a censored copy after transcription** queues a censored copy after every newly verified transcript; leave it off to review the transcript first. **Automatically process YouTube downloads** sends a completed YouTube import through Ready, transcription, and the censored-copy queue. Both are off by default and saving either choice never starts files already in Ready. The default input folder is `%USERPROFILE%\Documents\Expletive Deleted\Ready`.
2. Add supported audio or video files to the configured Ready/Input folder, drag them into Queue, or use **Download from YouTube** for an individual video you are authorized to download. YouTube import requires the optional `yt-dlp` component.
   If YouTube requires sign-in or verification, the app shows a browser-session dialog. Choose the visible browser session only when you are ready to retry. **Open YouTube** is optional, opens no browser until you press it, and does not retry the download. Your password is never requested or handled by Expletive Deleted; yt-dlp reads the selected browser's local cookies.
3. Return to **Queue** and choose an action for one file:
   - **Transcribe only** creates and verifies a transcript without creating media output.
   - **Retranscribe** replaces an existing transcript with a newly generated, verified transcript while retaining any finished output.
   - **Archive** moves an original with a verified transcript or output to Processed when that file has no queued or active job. Other files can continue processing or waiting in the queue.
4. To process selected files, check Ready rows and choose **Queue transcript only**. In the **Transcribed** view, check verified transcript rows and choose **Queue censor**. Valid files remain queued if another selected file is rejected.
5. Use the status filters and sort control to inspect Ready, Queued, Active, Transcribed, or Finished files. The active row can be cancelled from its Actions group; waiting rows show their queue position and can be removed independently.
6. Review discovered potential profanity and update the local censor or ignore policy in the app when appropriate.

Downloads, copies, transcription, and censoring use separate queue states. Transcription and censoring share the media-processing resources, so only one of those heavy jobs runs at a time; the other remains Queued until resources are available. You can add files to Ready while another job is active; imported files are not queued automatically. Completed output is written to Finished/Output. Transcripts are reusable, and originals remain in Ready/Input unless explicitly archived.

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
.\.venv\Scripts\python.exe manage_dependencies.py plan --component ytdlp
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
