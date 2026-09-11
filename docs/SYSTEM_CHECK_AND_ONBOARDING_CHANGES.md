# System Check and Onboarding for Private Python

This document defines the system-check behavior that accompanies the
Python-only installer policy in
[BUNDLED_RUNTIME_PACKAGING_PLAN.md](BUNDLED_RUNTIME_PACKAGING_PLAN.md).

## Readiness groups

| Group | What the app checks | Blocks local processing? | Recovery |
| --- | --- | --- | --- |
| Private Python | The packaged bridge is running from the app-owned Python runtime | Yes | A startup failure is an application repair or reinstall issue. |
| Transcription packages | Pinned `faster-whisper`, CTranslate2, PyAV, NumPy, `better-profanity`, and Hugging Face Hub versions | Yes | Review and approve installation into private Python, then verify. |
| Media tools | Compatible FFmpeg and FFprobe executables | Yes | Locate existing tools or approve managed setup. |
| Speech model | The selected model files and supported revision | Yes | Locate an existing model or approve the selected download. |
| YouTube tools | yt-dlp and Deno | No for local files | Locate or approve setup before importing from YouTube. |
| H.264 conversion | A working encoder when H.264 output is selected | No when preserving source video | Select another output mode or a compatible FFmpeg installation. |
| Hardware acceleration | CUDA and the selected compute type | No | Keep CPU transcription available. |

`processing_ready` is true only when private Python, the transcription packages,
FFmpeg, FFprobe, and the selected model are ready. yt-dlp and Deno are separate
YouTube capabilities.

## Packaged-runtime behavior

The presence of private Python does not imply that processing packages or media
tools came with the application. A missing processing package is a setup state,
not evidence that the installer is damaged. Packaged mode must continue to
inspect the application-managed component root, compatible user installations,
and saved path overrides.

The Settings page keeps FFmpeg and FFprobe overrides available in packaged
builds. Its copy distinguishes the included private Python runtime from the
separately approved processing components.

If private Python or the packaged backend cannot start, the application shows
repair guidance. It must not fall back to a system Python interpreter after a
valid packaged-runtime manifest has selected the private interpreter.

## First-run setup

The **Prepare this computer** step lists:

1. Transcription packages.
2. FFmpeg and FFprobe.
3. YouTube tools.
4. The selected Whisper model.

Each missing item remains visible. The primary setup action creates a plan but
does not begin a download. The consent dialog presents source, purpose, version,
license, destination, network use, and size when known. The user may cancel the
dialog without changing the computer.

The walkthrough may continue with warnings so users can review folders and
settings, but processing controls remain unavailable until required components
verify successfully. Outside onboarding, the setup band offers the package,
media-tool, and model actions again so an incomplete or cancelled setup is
recoverable.

## Parent-facing language

- Say **Private Python is included** only for the interpreter and bootstrap.
- Say **Install transcription packages** for the pinned Python dependencies.
- Say **Set up FFmpeg and FFprobe** for media tools.
- Say **Set up YouTube tools** for yt-dlp and Deno.
- Never claim that processing packages, FFmpeg, yt-dlp, Deno, or a model came with the installer.
- Explain that all processing stays local and setup does not change source media.

## Acceptance criteria

On a clean Windows x64 computer, the application opens using private Python and
shows every processing component as pending. Nothing downloads until the user
approves an exact plan. After setup, the app verifies each component and reports
processing readiness. Existing compatible tools can be selected, retry is
available after failure, and uninstalling or repairing the application does not
delete user media, settings, managed components, or models.
