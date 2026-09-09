# Bundled Windows Runtime Packaging Plan

## Purpose

Make the normal Windows installer usable on a clean computer without asking a parent to install Python, Python packages, FFmpeg, or FFprobe themselves.

The installer will include the runtime required to run the application, including the pinned yt-dlp executable. The Whisper `large-v3` model remains a separate, user-selected download because it is large and users should decide whether and where to install it. YouTube importing remains user-initiated and requires network access.

This is an implementation and release plan, not legal advice. The release owner must complete the license and artifact audit before changing the distribution policy.

## Product decisions

| Component | Installer policy | Reason |
| --- | --- | --- |
| Electron application | Include | Core desktop application. |
| Private Python runtime | Include | The application must run without a system Python installation. |
| Python backend and required packages | Include | They are part of the local processing service. |
| `faster-whisper`, CTranslate2, and PyAV | Include after binary audit | Required for local transcription and audio decoding. |
| FFmpeg and FFprobe | Include after LGPL-only build audit | Required for censoring, remuxing, and media inspection. |
| Whisper `large-v3` model | Do not include by default | Large download; the user chooses whether and where to obtain it. |
| yt-dlp | Include | Required application component; YouTube importing remains user-initiated. |

The installed application continues to process media locally. It must not upload source media, transcripts, or censor settings as part of setup.

## Video-output policy

New settings default to **Preserve source video**.

For a normal censorship job, the app copies the input video stream (`-c:v copy`), recreates only the censored audio, and preserves compatible subtitle streams. This avoids video encoding for the standard family-media workflow.

**Convert to H.264** remains an explicit user setting. It is appropriate only when the user asks for a more broadly compatible output. The bundled runtime must not silently fall back to `libx264` or another video encoder.

If a copied video stream cannot be combined with the selected output container and processed audio, the job must fail before replacing an output and explain that the user can select H.264 conversion or choose a compatible destination. It must not silently re-encode video.

The YouTube import pipeline needs separate qualification because it currently prepares H.264/AAC output. Before this plan ships, it must either preserve a compatible downloaded stream or clearly require the user to opt into H.264 conversion.

## Licensing and artifact requirements

### Python and Python packages

CPython's PSF License permits binary redistribution. The installer must retain the required Python copyright and license notices. Product copy may accurately say that the application contains Python, but must not imply Python Software Foundation endorsement. See the [Python license](https://docs.python.org/3/license.html) and [PSF trademark policy](https://www.python.org/psf/trademarks/).

`faster-whisper` is MIT-licensed and uses PyAV to decode audio. PyAV is not optional in this architecture: faster-whisper documents that it decodes audio through PyAV and PyAV's FFmpeg libraries. See [faster-whisper 1.2.1](https://pypi.org/project/faster-whisper/1.2.1/).

The current PyAV Windows wheel is not approved for bundling. Its binary payload must be replaced with a PyAV build that links only to the audited LGPL FFmpeg library set. PyAV's own Windows-build project currently enables `x264` and `x265`, so its ordinary build output is also not an approved input. The release build must maintain a reviewed configuration that removes those libraries and links PyAV to the same approved FFmpeg shared libraries that ship with the app. The release audit must inventory every native DLL included by PyAV and every transitive wheel.

### FFmpeg and FFprobe

The bundled executables must be built without `--enable-gpl` and without `--enable-nonfree`. They must not include GPL libraries such as `libx264` or `libx265`.

For the selected FFmpeg build, retain and publish:

- The applicable LGPL text and third-party notices.
- Source corresponding exactly to the distributed binaries.
- The FFmpeg version, source revision, patches, and configure command.
- A release-page notice and in-app About notice identifying FFmpeg and linking to the matching source archive.

Use the [FFmpeg licensing checklist](https://ffmpeg.org/legal.html) as the release checklist. The current Gyan runtime and PyAV wheel must remain excluded until replaced because they contain GPL-enabled FFmpeg components.

### Release inventory

Before release, generate and review an SBOM and a shipped third-party-notices bundle from the exact installer contents. Update [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) with the final versions, licenses, source locations, and notices. The audit must reject unapproved GPL or nonfree FFmpeg options and binaries.

### Required release documents

The repository already has `THIRD_PARTY_NOTICES.md`. Extend it from the exact release inventory; do not rely on the current document's “not bundled” entries once the installer changes. The package process must create and ship:

- A `THIRD_PARTY_NOTICES.md` copy containing the full required MIT, BSD, Apache-2.0, PSF, LGPL, font, and Electron/Chromium notices for the artifacts actually installed.
- A `LICENSES/` directory containing every license text and required `NOTICE` file referenced by the release inventory.
- A machine-readable SBOM that identifies every Python wheel, native DLL, FFmpeg library, source revision, hash, and license.
- An FFmpeg source archive and build manifest containing the exact source revision, patches, configure command, compiler version, and hashes of shipped FFmpeg/PyAV binaries.
- A release-page and in-app About attribution for FFmpeg, Python, and the bundled third-party runtime.

GPL is an exclusion criterion for this bundled runtime. The package audit must fail if it finds a GPL-enabled FFmpeg build, `libx264`, `libx265`, or another GPL component. Therefore, the installer should not include GPL license text as though GPL software were approved; it should instead stop the release until the artifact is replaced or separately reviewed.

## Implementation phases

### 1. Preserve-video behavior

- Make `preserve_source` the default for new settings, configuration examples, and first-run settings.
- Retain an explicit **Convert to H.264** choice for users who request it.
- Remove silent `libx264` fallback from packaged-runtime behavior.
- Add regression tests for video stream copy, explicit conversion, and incompatible-container errors.

Existing settings are preserved: a user who already selected H.264 continues to receive H.264 conversion until changing that setting.

### 2. Build an audited runtime

- Select a supported CPython version and create a private runtime directory owned by the installed app.
- Package the Python bridge and its pinned dependencies for Windows x64.
- Build or obtain an auditable LGPL-only FFmpeg/FFprobe distribution.
- Build PyAV against the corresponding approved FFmpeg libraries.
- Record source revisions, hashes, build commands, and license artifacts in the release inputs.

### 3. Change Electron packaging

- Include the private Python runtime, backend, approved Python wheels/extensions, FFmpeg, and FFprobe in the Windows package.
- Update `backend-runtime.ts` to prefer the bundled Python runtime and retain the local-development `.venv` path for source checkouts.
- Remove system Python and `PATH` FFmpeg from the normal installed-app readiness requirement.
- Keep model readiness separate from the bundled application-runtime readiness, which includes yt-dlp.
- Change the package audit: allow only the approved bundled runtime artifacts and reject model payloads, unapproved FFmpeg binaries, and unapproved native DLLs.

### 4. Simplify first run

- On a clean Windows computer, launch directly into the walkthrough without a Python-install page.
- Display the user-selected Whisper model setup with source, destination, approximate size, disk requirement, progress, cancel/retry, and verification.
- Keep **Get required components** for development-only components not included in the installer; packaged builds must not offer a separate yt-dlp installer.
- Explain that no source media changes during setup.

### 5. Release qualification

- Test the installer on a clean Windows x64 VM with no Python, FFmpeg, or FFprobe on `PATH`.
- Verify transcription, censoring, video stream copy, audio-only processing, subtitles, cancellation, failure recovery, and the explicit H.264 setting.
- Verify the system does not use Electron's framework-owned `ffmpeg.dll` to satisfy the processing runtime check.
- Verify the installer contains the correct notices, matching source offer/archive, SBOM, and only approved native artifacts.

## Definition of done

A Windows customer can install and run Expletive Deleted without installing Python or media tooling. They choose whether to download Whisper `large-v3`; yt-dlp ships with the application and is used only when they choose YouTube importing. Standard censorship preserves video streams, and H.264 conversion happens only after an explicit user choice. The published installer and release page contain the verified license, notice, source, and artifact records for every bundled runtime component.
