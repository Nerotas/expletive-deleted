# Private Python Runtime Packaging Plan

## Purpose

Ship a Windows desktop application that starts without a system Python
installation while leaving every processing dependency under the customer's
control. The installer contains private CPython, its standard library, and the
pip bootstrap used by the reviewed setup flow. It does not contain processing
Python packages, FFmpeg/FFprobe, yt-dlp, Deno, or a Whisper model.

Processing remains local. Setup must not upload source media, transcripts,
dictionary entries, or settings.

## Product decision

| Component | Installer policy | Setup policy |
| --- | --- | --- |
| Electron application and Python backend source | Include | Installed with the application. |
| Private CPython, standard library, and pip | Include | Audited and verified during release packaging. |
| `faster-whisper`, CTranslate2, PyAV, NumPy, `better-profanity`, and Hugging Face Hub | Exclude | Install pinned versions into private Python only after approval. |
| FFmpeg and FFprobe | Exclude | Locate a compatible installation or obtain the managed runtime after approval. |
| yt-dlp | Exclude | Locate or download the pinned official executable after approval. |
| Deno | Exclude | Download the pinned official executable after approval when YouTube support needs it. |
| Whisper `large-v3` | Exclude | User-selected download to the application-data model cache. |

An Electron-owned root `ffmpeg.dll` remains part of the Electron framework. It
is Chromium codec support, not the external processing runtime, and must never
satisfy FFmpeg or FFprobe readiness.

## Consent-driven setup contract

Before obtaining a component, the application shows an immutable plan with the
component, purpose, version, source, license, destination, network requirement,
and estimated size when known. Nothing downloads or installs until the user
approves that exact plan.

Setup must:

- Preserve compatible existing components and allow supported locations to be selected.
- Install Python packages only into the application-owned private Python runtime.
- Store managed media tools and models under the per-user application-data root.
- Verify versions and expected files after each action.
- Make cancellation, failure, and retry understandable without touching media.
- Never modify the global Windows `PATH` or a system Python environment.

Pinned versions alone are not a complete integrity control. Managed downloads
must use an approved immutable source and checksum when the publisher provides
one. The Python-package flow should move to a reviewed wheel set or a
hash-locked requirements input before it is treated as a fully reproducible
offline artifact.

## Release artifact contract

The `app-runtime` payload contains only:

```text
python/
THIRD_PARTY_NOTICES.md
LICENSES/
sbom.cdx.json
runtime-manifest.json
```

The version-2 runtime manifest records Python, pip, license files, and a SHA-256
for every shipped file other than the manifest itself. The SBOM records only
Python and pip. Release verification launches the relocated Python executable,
checks pip, and rejects any additional installed Python distribution.

The static and packaged audits reject:

- FFmpeg, FFprobe, yt-dlp, and Deno executables.
- FFmpeg shared libraries and known encoder libraries.
- Processing Python packages or wheel files.
- Whisper models and Hugging Face model caches.
- Legacy all-in-one runtime manifests and unrecorded files.

The installer retains the license and notice material for every component it
actually distributes. Licenses for user-approved downloads are disclosed and
retained with their setup metadata rather than misrepresented as installer
contents.

## Video-output policy

New settings default to **Preserve source video**. Normal censoring copies the
video stream, recreates only censored audio, and preserves compatible subtitle
streams. **Convert to H.264** remains an explicit compatibility choice and may
run only when the selected user-managed FFmpeg provides a verified encoder.
The application must never silently change that choice or replace an original.

## Release qualification

Before publication:

1. Build the installer from a clean Windows x64 runner using the pinned private Python version.
2. Verify the relocated Python runtime and pip bootstrap before packaging.
3. Audit the unpacked application for excluded processing components and models.
4. Launch the packaged app with no system Python, FFmpeg, or FFprobe on `PATH`.
5. Confirm onboarding reports the processing packages, FFmpeg/FFprobe, YouTube tools, and model as separate setup items.
6. Approve setup and verify transcription, censoring, source-video preservation, YouTube setup, cancellation, and retry behavior.
7. Confirm failed or cancelled work retains source media and removes incomplete output when safe.

## Definition of done

A parent can install and open Expletive Deleted without installing Python. The
app clearly identifies every missing processing component and does not obtain
it until the parent reviews and approves the plan. The installer contains no
processing packages, external media tools, or speech model, and release audits
fail if any of those artifacts are accidentally introduced.
