# Phase 1 Task — User-Managed FFmpeg and Whisper Setup

## Context

The Profanity Censor application does **not bundle FFmpeg, ffprobe, faster-whisper models, or other externally retrieved processing assets** with the application installer.

The frontend already detects when required components are unavailable and shows a **System Ready** / missing-assets notification.

The next step is to let the user resolve those missing requirements from inside the Electron UI.

The application may assist with locating, downloading, installing, and validating these resources, but downloading must always be an explicit user action.

Do not silently download third-party resources.

---

# 1. Required User Experience

When the application detects missing requirements, display their status clearly.

Conceptual UI:

```text
System Setup

FFmpeg
Required for media processing.
Status: Not found

[ Locate Existing ]  [ Get FFmpeg ]


Whisper large-v3
Required for transcription.
Status: Not found

[ Locate Existing ]  [ Get Model ]


[ Check Again ]
```

If a component already exists:

```text
FFmpeg
Ready
C:\...\ffmpeg.exe
```

The user should be able to replace/change the configured location later through Settings.

---

# 2. Explicit User Permission

Nothing should be downloaded simply because the application starts or detects a missing dependency.

The user must initiate the action.

Before an external download begins, show a confirmation dialog containing at minimum:

- What is being retrieved
- Why the application needs it
- Where it will be stored
- The external source/provider
- Download size when reliably known
- A link to the relevant project/source where practical
- Cancel and Continue controls

Suggested wording:

```text
Get FFmpeg

Profanity Censor requires FFmpeg to process media.

If you continue, you are asking the application to retrieve FFmpeg
from an external source and store it locally for use by this application.

FFmpeg is a third-party project and is not developed or distributed
as part of Profanity Censor.

Source: <source>
Install location: <local destination>

[ Cancel ] [ Continue ]
```

Use equivalent wording for Whisper/model retrieval.

Do not present this text as a guarantee of legal rights or as a liability waiver.

---

# 3. Resource Locations

Separate user-owned media from application-managed runtime resources.

## User files

Continue using:

```text
%USERPROFILE%\Documents\Expletive Deleted\
```

for user-facing content such as:

```text
Ready\
Finished\
Processed\
Transcripts\
```

These are files the user is expected to browse, move, copy, or manage directly.

## Application-managed resources

Use a writable per-user application directory outside the packaged Electron application.

Target:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

Suggested structure:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
│
├── dependencies\
│   └── ffmpeg\
│       └── bin\
│           ├── ffmpeg.exe
│           └── ffprobe.exe
│
├── models\
│   └── whisper\
│       └── large-v3\
│
├── cache\
├── logs\
└── settings\
```

Do not place downloaded dependencies inside the Electron application's installed/package directory.

The application installation may be replaced during upgrades. Downloaded runtime assets should survive normal application updates.

---

# 4. FFmpeg Handling

Support two FFmpeg paths.

## Locate Existing

Allow the user to select an existing:

```text
ffmpeg.exe
```

Then locate/validate the associated:

```text
ffprobe.exe
```

where required.

Validation should verify that the executables:

- Exist
- Can be executed
- Return version information
- Provide the capabilities required by the application

Store the selected paths in application settings.

## Get FFmpeg

When the user explicitly chooses to retrieve FFmpeg:

1. Show the confirmation/disclosure UI.
2. Download to an application-controlled temporary location.
3. Validate the downloaded artifact.
4. Extract/install it beneath:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dependencies\ffmpeg\
```

5. Locate `ffmpeg.exe` and `ffprobe.exe`.
6. Validate them.
7. Save their absolute paths in application configuration.
8. Delete temporary download/extraction files when safe.
9. Re-run the System Ready check.

Do **not** modify the user's global Windows PATH merely to make the application's private FFmpeg installation available.

The backend should invoke the configured executable directly.

Example conceptual setting:

```json
{
  "runtime": {
    "ffmpeg_path": "C:\\Users\\User\\AppData\\Local\\ExpletiveDeleted\\dependencies\\ffmpeg\\bin\\ffmpeg.exe",
    "ffprobe_path": "C:\\Users\\User\\AppData\\Local\\ExpletiveDeleted\\dependencies\\ffmpeg\\bin\\ffprobe.exe"
  }
}
```

---

# 5. Whisper Model Handling

Treat the speech-recognition runtime and the model as separate concepts.

The application uses:

```text
faster-whisper
```

with the initial model:

```text
large-v3
```

The large-v3 model should not be bundled with the application installer.

When the model is missing:

```text
Whisper large-v3
Status: Not downloaded
[ Get Model ]
```

After explicit user approval, retrieve/cache the model beneath the application's model location:

```text
%LOCALAPPDATA%\ExpletiveDeleted\models\whisper\
```

Where practical, configure faster-whisper/model-loading code so the application owns and knows the cache location rather than relying on an undocumented/default cache directory.

Persist the resolved model location.

The final implementation must use the actual directory structure produced by the model-loading library rather than assuming a particular internal model-file layout.

---

# 6. Python / faster-whisper Dependencies

The existing Python project already has setup/bootstrap logic used to install its Python dependencies.

Reuse that installation mechanism where practical.

The Electron UI should become the user-facing entry point for that process.

Conceptually:

```text
Electron Setup UI
       ↓
User selects Install
       ↓
Existing bootstrap/setup logic
       ↓
Install required Python packages
       ↓
Validate faster-whisper
       ↓
Return structured status
```

Do not duplicate Python package-installation logic independently in the frontend if the existing installer can be adapted.

---

# 7. System Ready Status

The frontend should consume structured capability/status information from the backend.

Example:

```json
{
  "system_ready": false,
  "requirements": {
    "ffmpeg": {
      "available": true,
      "path": "C:\\...\\ffmpeg.exe",
      "version": "..."
    },
    "ffprobe": {
      "available": true,
      "path": "C:\\...\\ffprobe.exe"
    },
    "faster_whisper": {
      "available": true
    },
    "whisper_large_v3": {
      "available": false,
      "path": null
    }
  }
}
```

The frontend should not independently infer runtime readiness.

The backend is the source of truth.

---

# 8. Failure Handling

Handle expected failures explicitly:

```text
Download interrupted
No internet connection
Remote source unavailable
Invalid/corrupt archive
Extraction failure
Executable missing after extraction
FFmpeg fails validation
ffprobe missing
Whisper model download fails
Insufficient disk space
Permission failure
User cancels
```

A failed setup operation must return the user to a recoverable state.

Do not leave the application claiming the dependency is installed unless validation succeeded.

---

# 9. Settings

Add a Runtime / Components section to Settings.

Conceptually:

```text
Runtime Components

FFmpeg
C:\...\ffmpeg.exe
[ Change ] [ Verify ]

Whisper Model
C:\...\models\whisper\...
[ Change ] [ Verify ]

[ Check System ]
```

The exact paths may be considered advanced information, but they should remain inspectable.

---

# 10. Architecture Rule

Keep three concepts separate:

```text
Application package
    → Profanity Censor itself

Application-managed runtime directory
    → user-approved third-party processing components

Documents directory
    → user's media, transcripts, and outputs
```

Do not mix these locations.

The application should be able to be upgraded or replaced without deleting the user's media or requiring already-downloaded large models to be retrieved again.

---

# 11. Acceptance Criteria

This task is complete when:

1. Missing FFmpeg/Whisper requirements are visibly identified.
2. The user can locate an existing installation/resource.
3. The user can explicitly request retrieval of a missing resource.
4. Retrieval never begins without user action.
5. The user sees the source and destination before agreeing.
6. FFmpeg is stored outside the application package.
7. Whisper models are stored outside the application package.
8. Downloaded resources survive normal application upgrades.
9. FFmpeg is invoked through its configured absolute path rather than requiring global PATH modification.
10. The backend validates all components before reporting System Ready.
11. Failure/cancellation leaves setup recoverable.
12. Existing Python setup/bootstrap logic is reused where practical.