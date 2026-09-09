# System Check and Onboarding Changes for the Bundled Runtime

This document defines the product changes required when the Windows installer includes the private Python runtime, backend packages, faster-whisper, PyAV, FFmpeg, and FFprobe. It complements [BUNDLED_RUNTIME_PACKAGING_PLAN.md](BUNDLED_RUNTIME_PACKAGING_PLAN.md).

The model stays separate and user-selected. yt-dlp stays optional. A normal customer must never be asked to install Python, Python packages, FFmpeg, or FFprobe.

## 1. System check: required changes

### Replace the current dependency checklist

The current system check treats these as user-provided components:

- FFmpeg and FFprobe
- Python and the faster-whisper package set
- Whisper `large-v3`
- yt-dlp

After bundling, only the model is a required customer download. The check must divide results into these groups.

| Group | What the app checks | Blocks local processing? | User action when unhealthy |
| --- | --- | --- | --- |
| App components | Private Python, backend package imports, PyAV load, FFmpeg, FFprobe, and the bundled-runtime manifest | Yes | Explain that the installed app is damaged or incomplete. Offer **Restart**, **Open diagnostics**, and **Reinstall app** guidance. Do not offer Python, pip, FFmpeg, or path-selection actions. |
| Speech model | The selected Whisper model exists, is complete, and matches the supported revision | Yes | Show its download size and destination. Offer **Download model**, **Locate existing model**, retry, and cancel. |
| Optional YouTube support | yt-dlp exists and passes version verification | No | Show **Not installed** until the customer explicitly enables or uses YouTube import. Offer its separate approved setup. |
| Optional H.264 conversion | A compatible H.264 encoder is available only when the user selected Convert to H.264 | No for normal stream-copy processing | Explain that source-video preservation still works. Offer a link to Video output settings. Do not silently select `libx264` or change the setting. |
| Hardware acceleration | CUDA and selected compute type | No | Report as an informational performance choice. Keep CPU transcription available. |

### Make the bundled runtime an application-integrity check

The private runtime is owned by the installed application, so its failures are repair failures, not setup failures. The system check needs a distinct `app_runtime` result with individual details for:

1. The runtime manifest exists and identifies the installed runtime version.
2. `python/python.exe`, `ffmpeg/ffmpeg.exe`, and `ffmpeg/ffprobe.exe` exist at the expected private paths.
3. FFmpeg and FFprobe run and meet the approved version/configuration requirements.
4. Required backend imports load: faster-whisper, CTranslate2, PyAV, NumPy, better-profanity, and Hugging Face Hub.
5. PyAV can load the approved FFmpeg shared libraries.
6. The bridge is using the bundled FFmpeg and FFprobe paths, never Electron's root `ffmpeg.dll`, `PATH`, WinGet, or a user-selected executable.

The runtime-manifest hash/SBOM/source audit remains a release-build gate. The desktop check should verify installed paths, executable versions, and library imports; it should not make the customer wait while recalculating hashes for every installed binary on every launch.

### Change the readiness contract

Current `ready` combines FFmpeg, FFprobe, all Python dependencies, and the Whisper model. Retain `ready` as the processing gate, but expose the reason in a grouped form so the renderer does not infer product behavior from individual Python-package booleans.

The replacement capability payload should include fields equivalent to:

```text
app_runtime: ready | missing | invalid
app_runtime_detail: parent-facing repair instruction
app_runtime_source: bundled | development
speech_model: ready | missing | invalid
speech_model_name: large-v3
speech_model_path: local path when verified
speech_model_detail: source/revision/incomplete-download explanation
optional_ytdlp: ready | missing | invalid
h264_conversion: available | unavailable | not_requested
processing_ready: app_runtime ready AND speech_model ready
```

Keep the existing FFmpeg path/version and encoder details as developer diagnostics. They should not be the main customer-facing checklist. During source-checkout development, retain the external-runtime inspection path behind a `development` source so developers can use a repository `.venv` and explicitly configured tools without changing the packaged-app experience.

### Remove obsolete customer actions

Remove these actions from a packaged build:

- **Get Components** for Python or Python packages.
- **Get Components** or **Locate existing** for FFmpeg/FFprobe.
- The combined **Get required components** action when its plan includes Python or FFmpeg.
- Browser instructions to download Python.
- Settings fields that ask a customer to paste or browse to FFmpeg/FFprobe paths.

Do not remove the underlying diagnostics or development support until the packaged runtime has passed release qualification. In a packaged build, a missing bundled executable must lead to repair/reinstall guidance instead of a fallback to `PATH`.

### New parent-facing status copy

Use plain language and distinguish application repair from optional downloads.

| Condition | Heading | Supporting copy | Primary action |
| --- | --- | --- | --- |
| Bundled runtime verified, model missing | `Choose speech recognition` | `Expletive Deleted is ready to process files. Download the speech model when you are ready; it stays on this computer.` | `Download large-v3 model` |
| Model download incomplete | `Finish downloading the speech model` | `The previous download was not complete. You can retry without changing your files or settings.` | `Resume download` or `Start again` |
| Bundled runtime invalid | `Repair Expletive Deleted` | `A component that came with the app could not be verified. Your media and settings have not changed.` | `Restart` and `Open diagnostics` |
| yt-dlp absent | `YouTube downloads are optional` | `Install this only if you want to import an individual YouTube video. Local files do not need it.` | `Set up YouTube downloads` |
| H.264 unavailable after user selected it | `H.264 conversion is unavailable` | `Your usual workflow can still preserve the source video. Choose another video-output setting or use a computer with a compatible encoder.` | `Open video settings` |

## 2. Onboarding changes that follow from the system check

### Get ready step

Replace the four-row component installer with:

1. **Expletive Deleted components** — verified automatically; expandable details show that the app includes its local processing tools.
2. **Speech model** — the only required first-run download. Explain approximate download and disk space before consent.
3. **YouTube downloads (optional)** — separate opt-in row. Never include it in the model download consent.
4. **Video output** — informational confirmation that the default preserves source video. If the user chose H.264, surface availability without blocking the walkthrough.

The normal primary action should be **Download large-v3 model**, not **Get required components**. The step can continue only after the model is verified or the user explicitly exits the walkthrough; processing controls remain disabled until it is ready.

### Backend startup failure page

Replace `Install Python to continue` with a repair page for packaged builds. It must not link to Python downloads. A source-checkout/developer build may retain Python instructions behind an explicit development-only condition.

### Workflow settings step

Keep the existing automatic-flow choices:

- transcribed local file creates a censor queue entry;
- YouTube download then transcribe then censor, when optional yt-dlp is installed.

Explain that these choices do not start existing files and that YouTube automation is unavailable until yt-dlp is opted into. Add a concise video-output explanation: **Preserve source video** is the default; **Convert to H.264** is an explicit compatibility choice.

### Finish step and setup band

The finish summary should say:

- `Application components: verified` or `Needs repair`;
- `Speech model: verified` or `Not downloaded`;
- `YouTube downloads: optional / enabled / not installed`;
- selected video-output behavior.

Outside onboarding, replace the existing “System requirements” band with the same grouped status. It should route a damaged app to repair guidance, a missing model to model setup, and yt-dlp to the optional setup flow.

## 3. Implementation order

1. Add the grouped backend capability contract and tests for bundled, development, missing-model, invalid-runtime, optional-yt-dlp, and unavailable-H.264 states.
2. Change the packaged bridge/runtime lookup so it cannot fall back to system Python or `PATH` FFmpeg after a bundled-runtime manifest is present.
3. Update System Check, Setup Band, Finish, and Components onboarding UI to consume the grouped contract and remove obsolete customer actions.
4. Hide manual FFmpeg/FFprobe settings in packaged builds; retain them only in clearly marked developer diagnostics.
5. Add Electron smoke tests for a clean packaged runtime with a missing model, a damaged-runtime failure, model setup, and optional yt-dlp.
6. Visually review the walkthrough in light and dark modes at supported window sizes.

## Acceptance criteria

On a clean Windows computer, the system check says the application components are already verified, requests only the speech model, and labels yt-dlp optional. It never directs a parent to Python, pip, FFmpeg, PATH, or an executable location. A damaged bundled runtime is a repair/reinstall issue, a missing model is a user-approved download, and lack of an H.264 encoder does not block the default source-video workflow.
