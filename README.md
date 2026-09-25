# Expletive Deleted

![Expletive Deleted](docs/app-icon.svg)

**Create a family-friendly copy of audio or video without uploading your media.**

[Website](https://nerotas.github.io/expletive-deleted/) |
[Download for Windows](https://github.com/Nerotas/expletive-deleted/releases/latest) |
[Support development](https://ko-fi.com/nicholaserotas) |
[Quick start](QUICKSTART.md) |
[Troubleshooting](TROUBLESHOOTING.md)

![Expletive Deleted Queue](docs/app-queue.png)

Expletive Deleted is a Windows desktop application that transcribes spoken language locally, finds words you have chosen to censor, and creates a separate censored copy with FFmpeg. It is designed for parents and media owners who want control over what their family hears without sending private media or transcripts to a cloud service.

Version **1.4.1** is the current Windows release.

Expletive Deleted is free to use. [Ko-fi support](https://ko-fi.com/nicholaserotas) is optional and does not unlock features or priority service.

## What it does

- Processes supported audio and video locally on your computer.
- Lets you maintain your own censored-word and exclusion dictionaries.
- Offers a review-first **Transcribe only** workflow before media is changed.
- Imports an individual YouTube video into Ready and prepares it as a compatible local MP4.
- Creates censored copies with predictable full-audio muting or optional stereo dialogue cancellation.
- Keeps downloading, copying, transcription, and censoring visible as separate queue states.
- Keeps source files by default and never silently overwrites output.

Automated transcription and censorship are not perfect. Always review the transcript and finished media before sharing it.

Launching the app again restores and focuses the existing window. Dictionary edits from the desktop, command line, and background discovery share transaction protection; interrupted updates recover locally before the dictionary is shown.

Closing the desktop app cancels active work and allows up to 15 seconds for cleanup. New censored copies appear in Finished only after output verification succeeds. Settings cannot be saved while a local job or YouTube download is active; your draft remains available to save afterward.

## How it works

1. Add media by placing it in the configured **Ready** folder, dragging it into the Queue, or importing an individual YouTube video you are authorized to download.
2. Choose **Transcribe only** to create and review a local transcript.
3. Classify discovered words as **Censor** or **Ignore** in the Dictionary when needed.
4. In the **Transcribed** Queue view, select verified transcripts and choose **Queue censor** to create censored copies in **Finished**. Alternatively, enable **Automatically create a censored copy after transcription** in Settings to queue this step after each successful transcription.
5. Review the finished file. The original remains in Ready unless you deliberately archive it after success.

Transcoding uses only a persisted, verified transcript. It never begins a second Whisper transcription. Each processing job checks the original's full SHA-256 before using a transcript; startup and Queue polling do not hash your collection. **Retranscribe** creates a fresh transcript, retaining prior transcript versions in `.history` and leaving finished media in place.

Older files without source fingerprints appear as **Needs review**. They are preserved and excluded from bulk processing; they are never silently adopted or retranscribed. New artifact names retain the source extension, and finished copies have a `.provenance.json` companion file. Keep that companion with the output. See [source identity and compatibility](docs/SOURCE_IDENTITY_DISCUSSION_2026-09-25.md) for details and benchmark results.

## From YouTube to family-ready

Found a video you are allowed to download and want to share with fewer surprises? It takes just a few steps:

1. In **Queue**, choose **Download from YouTube**, paste an individual video URL, and add it to the queue.
2. Watch its download and compatibility preparation progress. The finished H.264/AAC MP4 appears in **Ready** automatically.
3. Choose **Transcribe**, review any detected words, then choose **Censor** to create the family-friendly copy in **Finished**.

YouTube import is local and user-initiated. The app verifies or retrieves the approved `yt-dlp` and Deno components during setup, gives the imported video its real title, and keeps the original downloaded file in Ready. If YouTube asks for sign-in or verification, Expletive Deleted pauses and asks before doing anything with a browser. Choose a visible browser session to retry, or explicitly choose **Open YouTube** to sign in; the app never opens a browser or uses browser cookies automatically, and never sees your password.

## Install on Windows

1. Download `Expletive-Deleted-Setup-1.4.1-x64.exe` from the [latest release](https://github.com/Nerotas/expletive-deleted/releases/latest).
2. Run the installer, then open **Expletive Deleted** from the Start menu or desktop shortcut.
3. Complete the setup checklist. The installer includes the private Python bridge; the app guides you through retrieving pinned Python packages, FFmpeg/FFprobe, yt-dlp, Deno, and the Whisper model when needed.
4. Complete the first-run walkthrough: Welcome, Get ready, Your settings, Add a file, Process safely, and Finish. It checks required components, prepares your dictionary, confirms folders and censoring preferences, and lets you choose the automatic local and YouTube workflows. It saves progress only when you choose **Save & Continue**.

The installer contains the Electron application and private Python bridge. It does not silently bundle or retrieve FFmpeg/FFprobe, yt-dlp, Deno, Python packages, or Whisper models. The walkthrough shows each missing component, its source, license, destination, and download impact before grouped approval.

## Requirements

- Windows x64
- Whisper `large-v3`, the supported accuracy baseline
- Disk space for the model, source media, transcripts, and finished copies

YouTube importing supports individual videos and uses a verified `yt-dlp` executable after YouTube setup is complete. It prepares them locally as H.264/AAC MP4 files in the Ready folder.

The first-run walkthrough verifies readiness. A network connection is needed only when you choose to retrieve a missing third-party component.

## Privacy and file safety

- Media, transcripts, dictionaries, and settings remain local by default.
- The application does not require an account or upload media for processing.
- Source files are retained after successful processing unless success-only archival is explicitly enabled.
- Failed or cancelled jobs retain the source and remove incomplete output when safe.
- Existing destination files are not silently replaced.
- Dependency downloads require an explicit, reviewed approval.

User media defaults to:

```text
%USERPROFILE%\Documents\Expletive Deleted\
├── Ready
├── Finished
├── Processed
└── Transcripts
```

Settings, the durable user dictionary, and explicitly retrieved runtime components are stored beneath `%LOCALAPPDATA%\ExpletiveDeleted`. Uninstalling the desktop application does not silently remove those files or user media.

## Censoring choices

**Drop audio** is the default and most predictable option. It silences the complete audio mix during each detected interval, including dialogue, music, and effects. It works with mono and stereo sources.

**Karaoke** attempts to cancel centered dialogue in stereo audio while retaining some music and effects. Results depend on the source mix, off-center speech may remain, and it is not appropriate for mono audio.

Recognized surround sources are handled separately: the front-center dialogue channel is censored before the selected surround output is preserved or downmixed.

## Supported media

Supported inputs include `.avi`, `.flv`, `.m4a`, `.mkv`, `.mov`, `.mp3`, `.mp4`, `.wav`, `.webm`, and `.wmv`. Audio-only jobs produce `.mp3`; video jobs produce `.mkv`.

## Develop from source

Source development requires:

- Node.js 22.12 or later
- Python 3.9 or later
- A repository-local `.venv`

Prepare the Python environment from the repository root:

```powershell
python setup.py
```

This checks the repo-local `.venv`, initializes the app settings and directories, and reports any missing approved development runtime components with their reviewed install plan. It never silently downloads the Whisper model. If the machine is running Microsoft Store Python, runtime assets are written to a stable per-user development root instead of a virtualized Windows Store path.

Start the complete Electron application from one terminal:

```powershell
cd frontend
npm install
npm run dev
```

Electron starts and owns the private Python bridge. Vite is used only to build and hot-reload the renderer; this is not a browser-hosted application.

Create the release-equivalent Windows installer from the repository root:

```powershell
.\scripts\build_local_release.ps1
```

This one command mirrors the GitHub release validation and packaging stages. It accepts Node.js 22.12.0 or later and uses Python 3.13.15 to match the release runtime, downloading and checksum-verifying the official Python archive temporarily when that version is not installed. It creates an isolated private Python runtime and writes the verified installer under `frontend/release/`. The package audit fails if the installer contains Whisper model payloads or accidental development binaries. Electron's framework-owned root `ffmpeg.dll` is Chromium codec support and cannot satisfy processing readiness.

## Releases and versioning

`frontend/package.json` records the source-tree application version. Run the synchronizer after choosing a version locally:

```powershell
cd frontend
npm version patch --no-git-tag-version
npm run version:sync
npm run version:check
```

The [Release workflow](.github/workflows/release.yml) lets the operator choose a `patch`, `minor`, or `major` increment from the latest stable release, or `none` to use the committed `frontend/package.json` version. It synchronizes version metadata in the build runner, runs backend, renderer, native, packaging, and installed-app checks, then creates a local metadata commit, pushes only its tag, and publishes the Windows installer. Generated release notes explicitly start at the immediately preceding stable release, so **What's Changed** contains only release-to-release changes.

After GitHub publishes the release, the [product-site workflow](.github/workflows/deploy-pages.yml) deploys the tagged `docs/` directory to GitHub Pages. Set GitHub Pages to **GitHub Actions** as its build source before relying on this deployment.

Repository Actions must have **Read and write permissions** so the workflow can push the release tag and create the GitHub Release. It never pushes commits to protected `main` or creates a release pull request. A failed validation does not tag or publish the release.

## Validation

Run the complete Windows validation flow from the repository root:

```powershell
.\scripts\run_all_tests.ps1
```

This runs the backend suite, frontend tests, typecheck, lint, development Electron smoke, setup-first package build/audit, and packaged Electron smoke. Use `-SkipPackaged` when you only need the code and development-app checks.

Backend, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Desktop, from `frontend/`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
npm run smoke
```

## Architecture

The [Python backend module guide](backend/README.md) describes runtime inspection, approved setup, processing, and desktop protocol ownership. The desktop Python entrypoint delegates to `backend/desktop/`; compatibility exports preserve existing CLI imports.

```text
backend/                  Python source of truth for settings, jobs, policy, and media safety
frontend/electron/        Native window, lifecycle, preload API, and Python child process
frontend/src/             React renderer and typed desktop client
resources/                Factory dictionary resources
scripts/                  Bootstrap, diagnostics, and maintenance commands
tests/                    Backend regression tests
docs/                     Product site and design documentation
```

The renderer uses React Router, TanStack Query, and React Hook Form. It communicates only through the context-isolated typed preload API. `nodeIntegration` remains disabled, and the renderer receives no arbitrary filesystem, process, or shell access.

## Advanced command line

The desktop application is the normal user experience. The compatibility CLI remains available for development, automation, diagnostics, and headless operation:

```powershell
.\.venv\Scripts\python.exe diagnostics.py
.\.venv\Scripts\python.exe backend_app.py capabilities
.\.venv\Scripts\python.exe batch_process.py --list
.\.venv\Scripts\python.exe batch_process.py --report-only
```

See [QUICKSTART.md](QUICKSTART.md) for complete installed-app, source-build, and advanced CLI instructions.

## Project links

- [Product website](https://nerotas.github.io/expletive-deleted/)
- [Windows releases](https://github.com/Nerotas/expletive-deleted/releases)
- [Issue tracker](https://github.com/Nerotas/expletive-deleted/issues)
- [Support development on Ko-fi](https://ko-fi.com/nicholaserotas)
- [Desktop developer notes](frontend/README.md)
- [Windows path protections](docs/HP-07_IMPLEMENTATION_2026-09-17.md) and [verified publication](docs/HP-06_IMPLEMENTATION_2026-09-17.md)
- [Verified playback and native dictionary file operations](docs/HP-02_IMPLEMENTATION_2026-09-17.md)
- [Troubleshooting](TROUBLESHOOTING.md)

Component setup and onboarding save only their intended settings changes. If a path changed during setup, **Review component settings** offers **Keep current** or **Use verified**. Completed downloads are retained; applying a choice verifies the existing component without reinstalling it.

The walkthrough preserves newer component paths and unrelated preferences at every step. If one of your edits conflicts, **Settings changed elsewhere** offers **Keep current** or **Use my edit**. Cancel keeps your draft on the same step. A further change requires another choice before saving.

If setup loses contact with the local service, it shows **Reconnecting to setup** with elapsed time for up to 30 seconds. **Retry connection** checks existing progress only. If the service exits, recovery appears immediately. **Restart app** is explicit; completed files stay on your computer, and any further installation requires reviewing and approving a fresh plan.
