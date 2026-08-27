# Profanity Censor Desktop App — Master Project Handoff

## Status

This document is the consolidated project handoff for the Profanity Censor application.

It incorporates and supersedes the earlier:

- Plan V2 — Profanity Censor Desktop App + React Native Frontend
- 2026-08-24 revisions
- Phase 1 frontend/configuration supplement
- Repository strategy supplement
- Subsequent UI, batch, processing, censoring, directory, distribution, and dependency-management decisions

Where an older decision conflicts with a newer decision recorded here, **this document takes precedence**.

---

# 1. Project Purpose

The project began as a Python CLI-oriented media transcoding/censoring utility.

It has evolved into a complete desktop application focused specifically on:

> Automatically transcribing video/audio, detecting profanity, and censoring the detected profanity locally.

The application should preserve the existing successful Python processing pipeline rather than rewriting it merely to support a GUI.

The product is **not** primarily a generic transcoder.

Generic media transcoding remains useful only where it supports the profanity-censoring workflow.

The core user-facing objectives are:

```text
Find media
    ↓
Transcribe
    ↓
Detect profanity
    ↓
Censor when requested
    ↓
Produce finished output
```

The application should make this workflow visible, configurable, and easy to manage without requiring the user to operate the existing CLI manually.

---

# 2. Current Project Positioning

The project is no longer being designed primarily as a commercial paid application.

Current direction:

```text
Portfolio-quality desktop application
+
public/source-visible repository
+
optional free downloadable application
+
optional voluntary support link
```

Possible voluntary support mechanisms such as Ko-fi may be added later, but payment, subscriptions, entitlements, activation, and licensing systems are **not part of the censorship engine or Phase 1 application architecture**.

The project should still be engineered to a high standard because a primary objective is demonstrating real-world software-development capability.

The project should look and behave like a real end-user application rather than a developer demonstration.

---

# 3. Public Repository and Distribution Strategy

## 3.1 New repository

Create a **new repository** for the desktop application.

The existing CLI/transcoder repository should not simply continue expanding indefinitely into the desktop application.

The project has crossed a meaningful product boundary:

```text
Old project
CLI-oriented censorship/transcoding utility

New project
Installed desktop profanity-censor application
```

A dedicated application repository provides a cleaner representation of the new product architecture.

Do not create the new repository merely as a GitHub fork unless there is a specific reason to preserve a formal GitHub parent/fork relationship.

A normal new repository is preferred.

---

## 3.2 Preserve the old repository

Before migrating development:

1. Preserve the known-working CLI implementation.
2. Tag or otherwise identify the last stable working baseline.
3. Preserve relevant tests.
4. Preserve representative media-processing behavior.
5. Avoid unnecessary refactoring of the old repository.

The old repository becomes:

```text
Historical baseline
Regression reference
Source of proven censorship logic
Reference CLI implementation
```

It should not remain a second independently evolving implementation of the same censorship engine.

Once migration succeeds, primary development moves to the new application repository.

---

## 3.3 New repository identity

The new repository represents:

> **Profanity Censor — Desktop Application**

It does not represent:

> Generic Python Transcoder With a GUI

The repository structure, README, screenshots, documentation, tests, packaging, and release strategy should reinforce that distinction.

---

## 3.4 Public repository

Current intended direction is for the new application repository to be publicly visible.

This gives the project portfolio value by exposing:

- Architecture
- React/Electron implementation
- Python backend
- Service boundary
- Media-processing orchestration
- Settings architecture
- File lifecycle management
- Asynchronous processing
- Progress reporting
- Cancellation
- Speech recognition
- Audio manipulation
- Testing
- Packaging
- Dependency bootstrap
- Release engineering

### Open decision — repository license

A public repository does not by itself determine which license should be applied to the project's own source code.

Before public release, choose an appropriate license or intentionally choose not to grant a conventional open-source license.

This decision is separate from the architecture described here.

---

# 4. Free Downloadable Application

The public repository may also provide a free Windows application download.

Possible delivery mechanisms include:

```text
GitHub Releases
Standalone Windows installer
Other project download page
```

The free downloadable application is intended to make the project genuinely usable rather than requiring every user to build Electron and Python code manually.

No paid feature restrictions are currently planned.

Possible future About-screen links:

```text
Project Website
GitHub Repository
Report an Issue
Support This Project
```

A voluntary support link should remain peripheral to the product.

The application should work normally whether or not a user supports the project financially.

---

# 5. Core Processing Architecture

Preserve the successful existing workflow.

Current conceptual engine:

```text
Media file
    ↓
faster-whisper
    ↓
word-level timestamps
    ↓
ProfanityCensor.detect_profanity()
    ↓
structured censor intervals
    ↓
FFmpeg filter generation
    ↓
FFmpeg subprocess
    ↓
censored output
```

The existing `ProfanityCensor` implementation remains the foundation.

Do not rewrite the censorship algorithms solely to accommodate Electron.

The major architectural change is moving orchestration away from CLI-only control into an application/service layer.

---

# 6. Target Application Architecture

```text
┌───────────────────────────────────────┐
│ Electron + React Desktop Application  │
│                                       │
│ • Queue                               │
│ • Settings                            │
│ • File status                         │
│ • Progress                            │
│ • Configuration                       │
│ • Error display                       │
│ • Cancellation                        │
│ • Future review tools                 │
└───────────────────┬───────────────────┘
                    │
                    │ Structured JSON
                    │
                    ▼
┌───────────────────────────────────────┐
│ Local Python Backend                  │
│                                       │
│ • File discovery                      │
│ • Job lifecycle                       │
│ • Settings                            │
│ • Progress events                     │
│ • Cancellation                        │
│ • Capability detection                │
│ • ProfanityCensor orchestration       │
└─────────────┬─────────────────────────┘
              │
              ├──────────────────────┐
              ▼                      ▼
┌──────────────────────┐   ┌─────────────────────┐
│ faster-whisper       │   │ FFmpeg / ffprobe    │
│                      │   │                     │
│ transcription        │   │ audio filtering     │
│ word timestamps      │   │ muxing              │
│ CPU / CUDA           │   │ stream copy         │
└──────────────────────┘   │ optional H.264      │
                           └─────────────────────┘
```

The frontend is the **presentation and control layer**.

Python remains the **processing layer**.

FFmpeg remains a separate executable process.

---

# 7. Frontend Framework

Use:

```text
Electron + React
```

React Native is no longer the planned desktop framework.

Reasons established during planning include:

- Existing React familiarity
- Mature Electron desktop ecosystem
- Strong examples of Electron spawning local backend processes
- Windows/macOS/Linux desktop potential
- Desktop-app behavior without using a browser-hosted interface

Tauri may be interesting as a later technical exercise, but is not the Phase 1 framework.

---

# 8. Platform Scope

## Phase 1

Windows.

Primary target:

```text
Windows desktop
```

Initial distribution:

```text
Standalone installer
```

A Microsoft Store release is no longer required for Phase 1.

---

## Future

macOS remains a future desktop target after the Windows architecture is stable.

Linux may be technically possible because of Electron/Python/FFmpeg portability, but is not a current product commitment.

---

## Out of scope

For the current project:

- Browser-hosted application
- iPhone
- iPad
- Android
- Cloud media processing
- Cloud transcription
- OpenAI API dependency
- SaaS architecture
- Account system
- Subscription system

---

# 9. Local Processing and Privacy

Normal censorship should occur locally.

Media should not need to be uploaded to an external service.

Normal operation should not require:

- Cloud transcription
- Transcript upload
- Media upload
- OpenAI API
- Remote inference service

Internet access may be required for:

- Dependency installation
- Whisper model retrieval
- Application updates
- Optional project links
- Optional dictionary updates

After required dependencies and models are installed, normal processing should be capable of remaining local.

---

# 10. Third-Party Dependency Distribution Decision

This is a major revision from the earlier packaging plan.

The project should **not bundle FFmpeg or Whisper directly into the repository/application distribution**.

Instead:

```text
Profanity Censor application
        ↓
checks dependencies
        ↓
dependency missing
        ↓
asks user for permission
        ↓
retrieves/installs dependency separately
        ↓
verifies installation
        ↓
uses installed dependency
```

This follows the conceptual model already used by the existing Python project, where users run installation/setup logic that installs required components.

The desktop application should convert that existing developer-oriented setup experience into an understandable end-user setup experience.

---

# 11. First-Run Dependency Setup

The application should check for required components during setup or first launch.

Possible presentation:

```text
Profanity Censor Setup

Required Components

FFmpeg
Not installed
[ Locate Existing ] [ Install ]

faster-whisper
Not installed
[ Install ]

Whisper large-v3 model
Not downloaded
[ Download ]

[ Continue ]
```

Nothing should be downloaded or installed silently.

The application should obtain user permission before retrieving external components.

---

# 12. Existing Dependency Installer

The current Python project already includes an installation/setup mechanism used to install required dependencies.

That existing automation should be reused where practical.

Do not create a completely independent dependency-management implementation merely because Electron has been added.

Conceptually:

```text
Existing setup/bootstrap logic
          ↓
adapt for application use
          ↓
Electron setup UI
          ↓
user selects Install
          ↓
bootstrap performs installation
          ↓
application verifies result
```

The frontend provides the interface.

The underlying installer remains responsible for performing and validating setup.

---

# 13. Dependency Categories

Treat these separately.

## FFmpeg / ffprobe

Required for:

- Media inspection
- Audio censorship
- Audio encoding
- Muxing
- Video stream copy
- Optional H.264 video encoding

The application should:

```text
detect
locate
validate
report version
report capabilities
```

Users may either:

- Point the application to an existing installation
- Allow the setup process to retrieve/install one

The project itself does not ship an FFmpeg executable inside the repository or application package.

---

## faster-whisper

Required by the Python processing backend.

Installation should occur as part of the approved dependency-bootstrap process rather than assuming a developer has already run `pip`.

---

## Whisper model

The planned initial model remains:

```text
large-v3
```

The model should not be bundled into the application download.

The application should ask the user before downloading it.

The application should display meaningful download/setup status.

Example:

```text
Preparing speech-recognition model

Whisper large-v3

Downloading...
1.4 GB / 3.0 GB
```

The exact displayed model size should be obtained from the actual model/download process rather than hardcoded from this example.

---

# 14. Application Data vs User Data

Maintain a clear distinction between:

```text
User-owned working files
```

and:

```text
Application-managed dependencies/runtime data
```

---

# 15. Default Windows User Directories

User media and reports should **not** default to `%LOCALAPPDATA%`.

Users need to see, move, inspect, copy, and manage these files directly.

Default root:

```text
%USERPROFILE%\Documents\Profanity Censor\
```

Suggested structure:

```text
Profanity Censor\
│
├── Ready\
├── Finished\
├── Processed\
└── Transcripts\
```

---

# 16. Directory Meanings

## Ready

Contains media available for processing.

This is the Phase 1 input/batch folder.

The application scans this directory and displays supported source files in the Queue.

---

## Finished

Contains successfully censored output.

Use `Finished` rather than `Transcoded` as the primary user-facing concept.

The app's objective is censorship, not transcoding.

---

## Processed

Optional destination for original source media after successful completion.

Files only move here when archive behavior is explicitly enabled.

Source files must never be archived after:

```text
Failure
Cancellation
Incomplete processing
```

---

## Transcripts

Contains transcription/profanity-report artifacts where retention is enabled or required.

This directory is particularly important for:

```text
Report Only
```

processing.

---

# 17. User-Controlled Directory Configuration

The defaults are conveniences, not requirements.

Users should be able to change:

```text
Ready/Input directory
Finished/Output directory
Processed/Archive directory
Transcript directory
```

The application should not assume the default directory names or locations after the user changes them.

Path values belong in persistent application settings.

---

# 18. Internal Application Storage

Application dependencies, caches, runtime files, logs, and similar internals may use an application-managed location such as:

```text
%LOCALAPPDATA%\ProfanityCensor\
```

Possible contents:

```text
runtime\
dependencies\
models\
cache\
logs\
settings\
```

The earlier objection to LocalAppData applies specifically to **user working files**, not invisible application internals.

Users should not normally need to manually manage runtime dependency files.

---

# 19. Phase 1 Batch Model

Phase 1 continues the existing folder-driven model.

Current workflow:

```text
Ready directory
     ↓
scan folder
     ↓
discover supported media
     ↓
display media in Queue
     ↓
process serially
```

The application processes one active media job at a time.

Do not introduce parallel Whisper/FFmpeg processing in Phase 1.

---

# 20. Future Queue/Input Model

The folder model should not become a permanent architectural limitation.

Future versions may support:

```text
Drag and drop
Browse/add individual files
Queue creation
Queue reordering
Queue removal
Multiple source locations
Manually selected batches
```

The backend job abstraction should therefore remain independent enough that the input-folder scanner is only one method of creating jobs.

---

# 21. Phase 1 Top-Level Pages

The application should remain intentionally simple.

Phase 1 requires only two top-level pages:

```text
Queue
Settings
```

Do not create a large dashboard/navigation structure without a demonstrated need.

---

# 22. Application Shell

A simple navigation model is appropriate:

```text
┌──────────────────────────────────────────────┐
│ Profanity Censor                             │
│                                              │
│ Queue                          Settings       │
├──────────────────────────────────────────────┤
│                                              │
│ Current page                                 │
│                                              │
└──────────────────────────────────────────────┘
```

A permanent complex sidebar is not required.

---

# 23. Queue Page Purpose

The Queue is the application's primary operational page.

It answers:

```text
What files are available?
What is currently processing?
What has already been transcribed?
What is being censored?
What is finished?
Did anything fail?
```

The Queue should be based on the configured input/library state, not console output.

---

# 24. Queue Table

Suggested conceptual structure:

```text
Queue

┌──────────────────────┬──────────────┬──────────────┬─────────────┐
│ File                 │ Status       │ Progress     │ Details     │
├──────────────────────┼──────────────┼──────────────┼─────────────┤
│ Movie One.mkv        │ Ready        │              │             │
│ Movie Two.mkv        │ Transcribing │ █████ 42%    │ ETA 04:12   │
│ Movie Three.mkv      │ Transcribed  │              │             │
│ Movie Four.mkv       │ Censoring    │ ███████ 71%  │ 182 FPS     │
│ Movie Five.mkv       │ Finished     │              │             │
└──────────────────────┴──────────────┴──────────────┴─────────────┘
```

Exact styling is not locked.

The important requirement is a clear table/list exposing the state of all discovered files.

---

# 25. Persistent File Status Model

Three primary persistent states describe what artifacts currently exist for a source file.

## Ready

The source file has been found and is available for processing.

Conceptually:

```text
Source media exists
No valid transcript currently associated
No finished censored output currently associated
```

---

## Transcribed

A valid transcription exists.

Profanity detection is included as part of the transcription stage.

This means the transcript has been parsed and the profanity results are available.

---

## Finished

A completed censored output exists.

Use:

```text
Finished
```

rather than:

```text
Transcoded
```

in the primary UI.

---

# 26. In-Progress Status Model

Two primary processing states are exposed to users.

## Transcribing

Includes:

```text
faster-whisper transcription
word timestamps
transcript generation
profanity parsing
profanity detection
```

Do not expose a separate `Detecting` lifecycle stage in Phase 1 unless later testing shows that it is meaningful enough to users.

Conceptually:

```text
Ready
  ↓
Transcribing
  ↓
Transcribed
```

---

## Censoring

Includes the FFmpeg/media-processing work used to apply approved censor intervals and create the finished file.

Use:

```text
Censoring
```

rather than:

```text
Transcoding
```

because it describes the user objective.

Conceptually:

```text
Transcribed
  ↓
Censoring
  ↓
Finished
```

---

# 27. Normal File Lifecycle

```text
Ready
  ↓
Transcribing
  ↓
Transcribed
  ↓
Censoring
  ↓
Finished
```

---

# 28. Exceptional Job States

The backend should still support exceptional states such as:

```text
Failed
Cancelled
```

These are not part of the normal lifecycle but must be visible when applicable.

A failed file should expose an understandable error rather than silently returning to Ready.

---

# 29. Processing Modes

Phase 1 requires two processing modes.

---

## Report Only

Purpose:

> Transcribe the source and detect profanity without producing censored media.

Workflow:

```text
Ready
  ↓
Transcribing
  ↓
Transcribed
  ↓
Stop
```

The transcript/profanity report is the output.

Suggested internal value:

```text
report_only
```

---

## Censor Media

Purpose:

> Perform the complete profanity-censor workflow.

Workflow:

```text
Ready
  ↓
Transcribing
  ↓
Transcribed
  ↓
Censoring
  ↓
Finished
```

Suggested internal value:

```text
censor
```

Avoid calling the mode simply `transcode`.

Video may be stream-copied, so transcoding does not necessarily describe what happens.

---

# 30. Review/Detailed Detection Workflow

The earlier project plan included manual detection review as an important feature.

Phase 1 now has only two **top-level** pages:

```text
Queue
Settings
```

This does not require permanently abandoning detection review.

If included in Phase 1, detection review should appear as a workflow launched from a Queue item rather than becoming a third top-level navigation page.

Possible future presentation:

```text
Queue
  ↓
Select Transcribed item
  ↓
Review modal / job detail / secondary workflow
```

Review capabilities remain useful:

```text
View detected profanity
Enable/disable individual detection
Adjust start time
Adjust end time
Seek/play around detection
Add missed interval
Approve censorship
```

The backend should therefore continue storing structured timestamps/detections even if the first minimal UI does not expose the complete review experience immediately.

---

# 31. Stereo Censoring

Stereo media supports two censorship methods.

---

## Drop Audio

`Drop Audio` means exactly:

> Mute/drop the stereo audio during the profanity interval.

Conceptually:

```text
normal audio
    ↓
detected profanity
    ↓
audio muted
    ↓
normal audio resumes
```

This is the straightforward censoring method.

---

## Karaoke

The existing karaoke method manipulates/flips a channel to remove or reduce centered dialogue.

The exact audio-processing implementation remains in the Python/FFmpeg backend.

The frontend should expose it as a user preference without duplicating the signal-processing logic.

Suggested setting:

```text
Stereo Censor Method

○ Drop Audio
○ Karaoke
```

---

# 32. Censor Padding

Preserve the existing configurable padding behavior.

Suggested default from the original plan:

```text
150 ms before
150 ms after
```

Settings:

```text
Censor Padding

Before word: [150] ms
After word:  [150] ms
```

The backend remains responsible for applying and validating the resulting censor interval.

---

# 33. 5.1 Censoring

5.1 audio uses a different approach from stereo.

The dialogue is handled through the front-center channel.

During profanity:

```text
Front Center
    ↓
mute/drop profanity interval

Other channels
    ↓
remain intact
```

The purpose is to preserve the music and effects channels while removing dialogue from the center channel during the censor interval.

Phase 1 does not need multiple 5.1 censor algorithms.

Initial behavior:

```text
5.1 profanity censor
=
drop/mute FC during profanity interval
```

---

# 34. 5.1 Final Audio Layout

After the profanity has been censored from the front-center channel, users may choose the final output layout.

---

## Preserve 5.1

```text
5.1 input
    ↓
censor FC
    ↓
5.1 output
```

---

## Downmix to Stereo

```text
5.1 input
    ↓
censor FC
    ↓
downmix censored result
    ↓
2-channel output
```

Important processing order:

> Apply profanity censorship to FC **before** performing the stereo downmix.

Suggested setting:

```text
5.1 Output

○ Preserve 5.1
○ Downmix to Stereo
```

---

# 35. Video Output

The earlier stream-copy-only limitation is no longer required as a product restriction because the project does not plan to distribute its own FFmpeg binary.

Phase 1 should support two realistic user preferences.

---

## H.264 Encode

Preferred when playback accessibility/compatibility is important.

Conceptually:

```text
Video
    ↓
encode H.264
```

The exact encoder available depends on the user's FFmpeg installation and detected capabilities.

The application should not assume that a specific encoder such as `libx264`, NVENC, QSV, or another implementation exists.

Capability detection should determine what can actually be used.

---

## Preserve Source Video

Stream-copy the original video.

Conceptually:

```text
-c:v copy
```

Only the audio path must be processed for censorship.

This avoids unnecessary video re-encoding and preserves the source video stream.

Suggested setting:

```text
Video Output

○ H.264
○ Preserve Source
```

---

# 36. Output Container

MKV remains a practical default from the original design because it accommodates a broad range of source streams and remuxing scenarios.

Container behavior should remain backend validated.

Do not assume that every requested stream/container combination is valid.

When output cannot be produced with the chosen settings:

```text
explain the incompatibility
```

rather than silently performing a destructive/unexpected fallback.

---

# 37. Profanity Dictionary

The existing text-based word-list architecture remains valid internally.

The frontend should eventually provide management tools for:

```text
View censored words
Search
Add word
Remove word
Add exclusion
Remove exclusion
Restore defaults
Import
Export
```

The frontend must not implement duplicate profanity-detection logic.

The backend remains the source of truth for parsing and validating the lists.

---

# 38. Settings Page

The Settings page contains persistent user preferences.

Suggested Phase 1 groups:

```text
Directories
Processing
Censoring
Audio Output
Video Output
Hardware / Runtime
Profanity Dictionary
Whisper
Source Handling
About
```

Not every advanced control has to be implemented in the very first UI pass.

The settings architecture should nevertheless support them.

---

# 39. Directory Settings

```text
Ready/Input Directory
Finished/Output Directory
Processed/Archive Directory
Transcript Directory
```

Defaults:

```text
%USERPROFILE%\Documents\Profanity Censor\Ready
%USERPROFILE%\Documents\Profanity Censor\Finished
%USERPROFILE%\Documents\Profanity Censor\Processed
%USERPROFILE%\Documents\Profanity Censor\Transcripts
```

All should be user configurable.

---

# 40. Processing Settings

```text
Processing Mode

○ Report Only
○ Censor Media
```

---

# 41. Stereo Censor Settings

```text
Stereo Censor Method

○ Drop Audio
○ Karaoke
```

---

# 42. Padding Settings

```text
Before censor interval
After censor interval
```

Initial defaults:

```text
150 ms
150 ms
```

---

# 43. Surround Audio Settings

Censorship behavior:

```text
5.1
→ mute/drop FC only
```

Output preference:

```text
○ Preserve 5.1
○ Downmix to Stereo
```

---

# 44. Video Settings

```text
Video Output

○ H.264
○ Preserve Source / Stream Copy
```

If H.264 is requested but the user's FFmpeg installation cannot satisfy the requested encoding path, disable the unavailable option or explain the failure clearly.

Do not silently choose an unrelated encoder/output.

---

# 45. Source File Handling

Default behavior:

```text
Never move or delete original
```

Optional:

```text
Archive original after successful processing
```

Suggested UI:

```text
Archive original after successful processing

○ Off
○ On
```

Default:

```text
Off
```

When enabled:

```text
Finished
    ↓
verify successful output
    ↓
move original to Processed
```

Never archive on:

```text
Failed
Cancelled
Incomplete
```

---

# 46. Whisper Settings

Initial intended model:

```text
large-v3
```

Do not expose a large model-selection menu in Phase 1 merely because faster-whisper supports additional models.

Accuracy remains central to the application purpose.

Possible settings:

```text
Model: large-v3
Processing device: Automatic / CPU / CUDA
Model/cache location
```

Model/cache location may remain advanced.

---

# 47. Hardware Detection

The backend should detect available capabilities rather than assuming them.

Whisper:

```text
CUDA available
    ↓ yes
CUDA
    ↓ no
CPU
```

FFmpeg:

```text
inspect installed build
    ↓
report available codecs/encoders/features
```

The frontend can disable unavailable options.

---

# 48. Phase 1 Settings Model

Conceptual configuration:

```json
{
  "directories": {
    "input": "%USERPROFILE%\\Documents\\Profanity Censor\\Ready",
    "output": "%USERPROFILE%\\Documents\\Profanity Censor\\Finished",
    "archive": "%USERPROFILE%\\Documents\\Profanity Censor\\Processed",
    "transcripts": "%USERPROFILE%\\Documents\\Profanity Censor\\Transcripts"
  },

  "processing": {
    "mode": "censor",
    "device": "auto"
  },

  "censoring": {
    "stereo_method": "drop_audio",
    "padding_before_ms": 150,
    "padding_after_ms": 150
  },

  "audio": {
    "surround_output": "preserve_5_1"
  },

  "video": {
    "mode": "h264"
  },

  "whisper": {
    "model": "large-v3"
  },

  "source": {
    "archive_after_success": false
  }
}
```

This is a conceptual settings schema.

Actual implementation types and validation rules may change during backend development.

---

# 49. Queue Progress Reporting

The existing Python implementation already exposes useful console progress information.

Phase 1 should migrate useful progress into structured application events.

Where reliably available, display:

```text
Progress percentage
Progress bar
Current stage
ETA
FPS
Elapsed time
Current file
```

Example:

```text
Movie.mkv

Transcribing
████████████████░░░░░░░░ 64%

ETA: 3m 42s
```

FFmpeg example:

```text
Movie.mkv

Censoring
███████████████████░░░░░ 78%

FPS: 184
ETA: 1m 09s
```

Do not fabricate metrics when the backend cannot reliably calculate them.

---

# 50. Structured Backend Events

Replace console scraping with structured messages.

Examples:

```json
{
  "event": "progress",
  "job_id": "123",
  "stage": "transcribing",
  "percent": 43.2
}
```

```json
{
  "event": "stage",
  "job_id": "123",
  "stage": "censoring"
}
```

```json
{
  "event": "detection",
  "job_id": "123",
  "word": "example",
  "start": 742.12,
  "end": 742.48
}
```

The console can remain available for diagnostics.

It should no longer be the primary application interface.

---

# 51. Backend Job Model

The backend should formalize the CLI workflow into jobs.

Conceptual internal state model may include:

```text
queued
transcribing
transcribed
awaiting_review
censoring
verifying
completed
failed
cancelled
```

The frontend does not need to expose every internal label directly.

User-facing mapping:

```text
queued/source discovered → Ready
transcribing            → Transcribing
transcribed/review      → Transcribed
censoring               → Censoring
completed               → Finished
failed                  → Failed
cancelled               → Cancelled
```

---

# 52. Cancellation

Cancellation remains required.

Backend responsibilities:

```text
track active Whisper work
track active FFmpeg process
request cancellation
terminate FFmpeg when required
clean incomplete temporary output
leave source untouched
mark job Cancelled
```

Cancellation must never trigger source archiving.

---

# 53. Backend Communication

The frontend/backend contract should use structured JSON.

The contract matters more than the exact transport.

Original recommended V1 transport remains reasonable:

```text
Electron
    ↓
localhost HTTP
+
WebSocket/event stream
    ↓
Python backend
```

Bind only to:

```text
127.0.0.1
```

Use a dynamically selected local port.

Use a per-launch random authentication token so unrelated local processes/pages cannot freely invoke the processing service.

Alternative future transports may include:

```text
named pipes
Unix domain sockets
child-process IPC
```

Keep application messages transport-independent where practical.

---

# 54. Suggested Backend API

Conceptual API:

```text
GET    /health

GET    /capabilities

GET    /settings
PUT    /settings

GET    /library

POST   /jobs
GET    /jobs
GET    /jobs/{id}

POST   /jobs/{id}/cancel

GET    /jobs/{id}/detections
PUT    /jobs/{id}/detections
POST   /jobs/{id}/approve

GET    /events
```

Folder/batch orchestration may later justify endpoints such as:

```text
POST /library/scan
POST /batch/start
```

Do not add endpoints merely for architectural appearance.

---

# 55. Library Endpoint

`/library` supports the Queue.

It should report known source files and their application state.

Conceptual response item:

```json
{
  "source": "C:\\Users\\User\\Documents\\Profanity Censor\\Ready\\Movie.mkv",
  "status": "ready",
  "transcript": null,
  "output": null
}
```

After transcription:

```json
{
  "source": "...\\Movie.mkv",
  "status": "transcribed",
  "transcript": "...\\Transcripts\\Movie.json",
  "output": null
}
```

After censorship:

```json
{
  "source": "...\\Movie.mkv",
  "status": "finished",
  "transcript": "...\\Transcripts\\Movie.json",
  "output": "...\\Finished\\Movie.mkv"
}
```

Exact persistence/storage format remains an implementation choice.

---

# 56. Capabilities Endpoint

The backend should report runtime availability.

Example:

```json
{
  "ffmpeg": true,
  "ffprobe": true,
  "ffmpeg_version": "...",
  "whisper": true,
  "model_large_v3": true,
  "cuda": true,
  "whisper_device": "cuda",
  "video_encoders": [
    "..."
  ]
}
```

Do not hardcode capabilities based on development-machine assumptions.

---

# 57. Dependency Setup UI

When required components are missing, the normal Queue should not simply fail.

Instead display an explicit setup state.

Example:

```text
Required Components

FFmpeg
Missing
[ Locate ] [ Install ]

Speech Recognition
Missing
[ Install ]

Whisper large-v3
Missing
[ Download ]

[ Recheck ]
```

The user should understand:

```text
what is missing
why it is needed
what will happen
where it comes from
```

before approving installation.

---

# 58. Dependency Verification

After setup, verify rather than assuming success.

FFmpeg verification may include:

```text
binary exists
ffmpeg responds
ffprobe responds
version available
required functionality available
```

Whisper verification may include:

```text
Python dependency import works
model cache exists
test initialization succeeds
```

Failures should be reported in the UI.

---

# 59. Licensing/Distribution Approach

[Unverified] The project planning rationale is to reduce redistribution complexity by **not redistributing FFmpeg or Whisper components in the repository/application package**.

Users install or retrieve those dependencies separately with explicit permission.

The project should still document:

```text
what dependencies it uses
where they come from
their relevant licenses
```

An About/Open Source Licenses section remains appropriate even for separately installed dependencies.

Do not treat this architecture as eliminating all possible licensing obligations.

Before any formal commercial distribution, legal requirements should be reviewed against the exact software and installation workflow being shipped.

---

# 60. H.264 and User-Installed FFmpeg

Because the application no longer plans to bundle a specific FFmpeg binary, the application may expose H.264 output when the user's FFmpeg installation supports an appropriate H.264 encoder.

The application should therefore operate on capability detection:

```text
User selects H.264
       ↓
backend checks installed FFmpeg
       ↓
compatible encoder exists?
       ├── yes → use configured/selected path
       └── no  → explain unavailable option
```

Do not assume a specific FFmpeg build.

Do not silently download a different FFmpeg build merely to satisfy a job unless the user explicitly approves such dependency changes.

---

# 61. Python Backend Packaging

The original plan included evaluating:

```text
PyInstaller
Nuitka
```

That packaging investigation remains relevant, but the dependency-bootstrap strategy changes what needs to be packaged.

Goal:

> End users should not need to understand the internal Python project structure in order to use the application.

A packaging proof-of-concept should evaluate:

```text
backend startup
Python runtime behavior
CTranslate2/faster-whisper installation
PyAV
CUDA
dependency bootstrap
model paths
antivirus behavior
signing
debugging
installer integration
```

Exact Python-runtime packaging remains a technical implementation decision.

---

# 62. Repository Structure

Target structure:

```text
profanity-censor/
│
├── backend/
│   ├── censor/
│   │   ├── engine.py
│   │   ├── transcription.py
│   │   ├── detection.py
│   │   └── filters.py
│   │
│   ├── jobs/
│   │   ├── manager.py
│   │   ├── models.py
│   │   └── events.py
│   │
│   ├── runtime/
│   │   ├── ffmpeg.py
│   │   ├── hardware.py
│   │   ├── whisper.py
│   │   ├── dependencies.py
│   │   └── paths.py
│   │
│   ├── settings/
│   └── service/
│
├── frontend/
│   └── Electron + React/
│
├── resources/
│   ├── profanity_censor_words.txt
│   └── profanity_exclusions.txt
│
├── scripts/
│   └── setup/bootstrap tooling
│
├── tests/
│
├── packaging/
│
└── docs/
```

This is a destination, not an instruction to perform a cosmetic refactor immediately.

---

# 63. Migration Strategy

Do not rewrite first.

Migration order:

```text
Old working repository
       ↓
freeze/tag working baseline
       ↓
create new application repo
       ↓
copy/migrate proven processing code
       ↓
make old behavior work in new repo
       ↓
verify regression tests
       ↓
add configuration layer
       ↓
add application service
       ↓
add Electron frontend
```

The first success criterion in the new repository is:

> The existing censorship workflow still works.

Not:

> The folder tree looks perfect.

---

# 64. CLI Role Going Forward

The new application repository may keep a CLI for:

```text
development
testing
debugging
automation
regression testing
```

But the CLI is no longer the primary user product.

Desired relationship:

```text
                  Electron UI
                      │
                      ▼
Shared service → Processing engine
                      ▲
                      │
                  Dev CLI
```

Do not maintain duplicate censorship logic in UI and CLI code paths.

---

# 65. Transcript Retention

**Open decision.**

The application clearly requires a transcript artifact at least long enough to support:

```text
Transcribed state
Report Only mode
Profanity detections
Possible review
Censoring
```

The final retention policy still needs to be decided.

Possible eventual choices:

```text
Always retain
Delete after Finished
User-configurable retention
```

The existence of the user-visible `Transcripts` directory suggests retention is useful, but the default cleanup policy is not yet locked.

---

# 66. Detection Review

The original plan treated review as a significant product feature.

Capabilities to preserve in the data model:

```text
Detected word
Timestamp
Start/end interval
Enabled/disabled
Manual adjustment
Manual interval creation
Playback around detection
Approval
```

A full editing timeline is not required for Phase 1.

Future graphical timeline:

```text
00:00 ───────────────────────────────────── 01:45:00
            ▲        ▲            ▲
          censor   censor       censor
```

The backend's timestamp data should remain structured so such UI can be added later without redesigning the engine.

---

# 67. Automatic Processing

The earlier plan included both:

```text
Automatic
Review First
```

The newer folder-batch approach introduces a useful Phase 1 processing model:

```text
Report Only
or
Censor Media
```

Manual review can be layered onto the `Transcribed` state.

Do not tightly couple transcription and FFmpeg censorship into one irreversible function call.

The service boundary should be capable of stopping after transcription.

---

# 68. Source Safety

Core rule:

> The source file is never modified in place.

Operations should create output separately.

Archiving is separate from censorship.

Failure/cancellation must leave the original untouched.

Temporary output should be cleaned appropriately when jobs fail or are cancelled.

---

# 69. Error Handling

Phase 1 should provide meaningful errors for conditions such as:

```text
FFmpeg missing
Whisper dependency missing
Whisper model missing
Unsupported media
FFmpeg failure
No writable output directory
Disk full
Output already exists
Invalid directory
Invalid settings
Dependency installation failure
No internet during requested model download
Cancellation
```

Do not expose only raw Python tracebacks to normal users.

Diagnostic logs may include deeper technical details.

---

# 70. Output Conflict Policy

**Open implementation detail.**

The app needs a defined behavior when:

```text
Finished\Movie.mkv
```

already exists.

Possible options include:

```text
Fail and ask user
Overwrite when enabled
Create versioned filename
```

Do not silently overwrite until a policy is explicitly chosen.

---

# 71. Progress Implementation

Use structured progress from:

```text
Whisper/backend processing
FFmpeg progress output
```

rather than scraping human-oriented console text wherever possible.

For FFmpeg, preserve useful metrics such as:

```text
frame
fps
processed time
speed
ETA
percent
```

when available and meaningful.

For transcription, expose:

```text
percent
elapsed
ETA
```

when the backend can calculate them reliably.

---

# 72. Queue Actions

Initial Queue actions may include:

```text
Start batch
Cancel active job
Retry failed job
Open output
Open output folder
Refresh/rescan
```

Avoid creating a large set of row actions in the first implementation.

The file/status presentation is more important than feature density.

---

# 73. Batch Processing Rule

Serial processing remains intentional.

Reasoning from the original plan:

```text
Whisper
GPU/VRAM
FFmpeg
CPU
disk I/O
```

may all compete for substantial resources.

A visible queue does not imply parallel processing.

Process:

```text
Job 1 active
Job 2 waiting
Job 3 waiting
```

Future parallelism should only be considered after resource testing.

---

# 74. Default Phase 1 UX

Conceptually:

```text
Launch app
    ↓
dependency check
    ↓
setup required?
    ├── yes → dependency setup
    └── no
    ↓
Queue
    ↓
scan Ready directory
    ↓
show discovered files
    ↓
user starts processing
    ↓
Transcribing
    ↓
Transcribed
    ↓
if Report Only → stop
    ↓
if Censor Media → Censoring
    ↓
Finished
```

---

# 75. Settings UX Philosophy

Settings should remain understandable to someone who wants to censor media, not someone who wants to operate FFmpeg manually.

Use product terminology:

```text
Censor Media
Drop Audio
Karaoke
Preserve 5.1
Downmix to Stereo
H.264
Preserve Source
```

Avoid unnecessary implementation terminology where a user-facing term exists.

---

# 76. About Page/Section

The application only requires Queue and Settings as top-level pages.

About can exist inside Settings.

Possible structure:

```text
Settings
  └── About
      ├── Version
      ├── GitHub
      ├── Report Issue
      ├── Open Source / Third-Party Licenses
      └── Support Project
```

No separate About navigation page is required.

---

# 77. Dependency Reproducibility

Even when dependencies are retrieved after installation, versions should not be uncontrolled.

The project should define/test compatible versions for:

```text
faster-whisper
CTranslate2
PyAV
NumPy
better-profanity
Electron
React
other backend/frontend packages
```

Release testing should occur against known dependency combinations.

Dependency updates should be intentional rather than automatically taking the newest version without regression testing.

---

# 78. Third-Party Inventory

Maintain documentation for third-party software used by the project.

Potential inventory:

```text
faster-whisper
CTranslate2
PyAV
FFmpeg
NumPy
better-profanity
Electron
React
other npm packages
other Python packages
```

Because FFmpeg and Whisper are installed separately, distinguish:

```text
Distributed with app
Installed/retrieved separately
Development-only dependency
```

---

# 79. Regression Testing

Protect the successful existing pipeline.

At minimum test:

```text
Stereo source
Stereo Drop Audio
Stereo Karaoke

5.1 source
5.1 FC censorship
5.1 preserve surround
5.1 → stereo downmix after censorship

H.264 source
H.265 source
other supported codecs

H.264 output
Preserve Source / stream copy

MKV
MP4
MOV

Large video
Multi-GB video

Unicode filename
Spaces in path
Long path where supported

CPU-only machine
NVIDIA/CUDA machine

FFmpeg already installed
FFmpeg missing
FFmpeg custom path
FFmpeg unsupported capability

faster-whisper installed
faster-whisper missing

large-v3 cached
large-v3 missing
model download cancelled
no internet during model download

Report Only
Censor Media

Ready → Transcribing
Transcribing → Transcribed
Transcribed → Censoring
Censoring → Finished

Cancellation during transcription
Cancellation during FFmpeg

FFmpeg failure
Disk full
Output already exists
Invalid path

No profanity detected
Many profanity detections
Overlapping profanity intervals

Multiple files in Ready directory
Serial batch progression

Archive off
Archive on after success
No archive after failure
No archive after cancellation
```

---

# 80. Golden Regression Data

Create representative known-good transcription and detection fixtures.

Goal:

```text
same source
+
known dependency versions
=
expected transcript/detections
```

Use these to detect behavioral changes after upgrades.

Perfect transcription identity may not always be realistic across runtimes/hardware, so tests should focus on behavior important to censorship accuracy.

---

# 81. Development Phases — Updated

## Phase 0 — Freeze existing CLI baseline

- Identify known-working commit
- Tag release/baseline
- Preserve tests
- Preserve representative inputs
- Document current installation process
- Document current censorship behavior

Goal:

> Never lose the proven implementation while building the application.

---

## Phase 1 — Create new application repository

- Create dedicated `profanity-censor` application repository
- Establish README/project identity
- Set up backend/frontend/docs/tests structure
- Do not bundle FFmpeg or Whisper binaries/models
- Decide public-repo license before formal publication

Goal:

> Establish the new product boundary.

---

## Phase 2 — Migrate processing engine

Bring over:

```text
ProfanityCensor
transcription
profanity detection
filter generation
FFmpeg invocation
current batch logic
word/exclusion lists
relevant tests
```

Reproduce the current CLI workflow before large refactors.

Goal:

> Existing processing works inside the new repository.

---

## Phase 3 — Configuration and directory layer

Implement:

```text
Documents\Profanity Censor defaults
Ready
Finished
Processed
Transcripts

persistent settings
path validation
user overrides
```

Goal:

> Remove hardcoded folder assumptions.

---

## Phase 4 — Dependency/bootstrap layer

Adapt current setup logic.

Implement:

```text
dependency detection
FFmpeg locate/install
faster-whisper install
large-v3 download
user permission
verification
error handling
```

Goal:

> A non-developer can satisfy prerequisites from the application workflow.

---

## Phase 5 — Backend service boundary

Implement:

```text
settings
library scanning
job model
statuses
structured progress
events
cancellation
capability detection
error objects
```

Keep the censorship engine intact where possible.

Goal:

> The processing engine is controllable without scraping CLI output.

---

## Phase 6 — Processing options

Implement/verify:

```text
Report Only
Censor Media

Stereo Drop Audio
Stereo Karaoke

5.1 FC censorship
Preserve 5.1
Downmix to Stereo

H.264 output
Preserve Source video

padding
```

Goal:

> User settings map cleanly to backend processing behavior.

---

## Phase 7 — Electron + React Phase 1 UI

Implement two top-level pages:

```text
Queue
Settings
```

Queue:

```text
file table
status
progress
ETA
FPS
start
cancel
retry/error
```

Settings:

```text
directories
processing mode
censor mode
padding
audio output
video output
archive behavior
Whisper/runtime
dictionary
About
```

Goal:

> Replace normal CLI operation with a usable desktop interface.

---

## Phase 8 — Detection-review UX

If not completed during the initial Queue implementation:

- Open Transcribed job
- Show detected profanity
- Toggle censor
- Adjust timing
- Add missed interval
- Playback/seek
- Approve

This does not need to become a third permanent navigation page.

Goal:

> Allow human verification before expensive censorship processing.

---

## Phase 9 — Windows packaging

Produce a downloadable Windows application.

Application package should contain the Profanity Censor application itself, but not bundled FFmpeg/Whisper model assets under the current dependency policy.

Validate:

```text
clean machine installation
first launch
dependency setup
model retrieval
backend startup
filesystem permissions
updates
uninstall
```

---

## Phase 10 — Public release / portfolio polish

Prepare:

```text
README
screenshots
architecture explanation
setup instructions
contribution information
issue templates
license decision
dependency documentation
privacy explanation
release notes
download instructions
```

Optional:

```text
Support project / Ko-fi
```

Goal:

> The repository should be understandable to both users and technical reviewers.

---

## Future Phase — macOS

After Windows is stable:

```text
reuse React UI
reuse JSON/service contract
reuse Python processing engine
reuse censorship logic
```

Solve separately:

```text
packaging
dependency bootstrap
FFmpeg discovery
CUDA differences
Apple Silicon
signing
notarization
filesystem paths
```

---

# 82. Explicit Locked Decisions

The following should be treated as current project decisions.

```text
Product:
Profanity censorship application

Core engine:
Existing Python/faster-whisper/FFmpeg pipeline

Frontend:
Electron + React

Backend:
Python

Processing:
Local

Cloud processing:
Not required

Initial platform:
Windows

Top-level Phase 1 UI:
Queue + Settings

Batch:
Input-folder driven

Batch concurrency:
Serial

Default user root:
Documents\Profanity Censor

User directories:
Ready
Finished
Processed
Transcripts

Persistent normal statuses:
Ready
Transcribed
Finished

In-progress statuses:
Transcribing
Censoring

Transcribing includes:
Whisper + profanity detection

Processing modes:
Report Only
Censor Media

Stereo censorship:
Drop Audio
Karaoke

5.1 censorship:
Mute/drop Front Center during profanity

5.1 output:
Preserve 5.1
or downmix censored audio to stereo

Video:
H.264 encode
or Preserve Source / stream copy

Source archive:
Off by default
Success only

Whisper model:
large-v3 initially

Repository:
New dedicated application repo

Old repo:
Preserve as known-working baseline

Repository visibility:
Public/source-visible direction

Download:
Free downloadable Windows application is an intended option

Monetization:
No paid entitlement system currently

Support:
Optional voluntary support link may be added

FFmpeg:
Not bundled in repository/application distribution

Whisper:
Not bundled in repository/application distribution

Dependency installation:
User-approved setup/bootstrap

Existing installer:
Reuse where practical

Browser UI:
Rejected

Mobile:
Out of scope
```

---

# 83. Remaining Open Decisions

These remain unresolved and should not be silently decided during implementation.

## Project license

Choose license/rights for the public repository.

---

## Transcript retention

Decide whether completed transcripts:

```text
remain
are deleted
or follow user setting
```

---

## Output conflict handling

Decide what happens when output already exists.

---

## Exact H.264 encoder preference

Capability detection is required.

The default encoder-selection policy still needs implementation/testing.

---

## Dependency source policy

The application needs a defined and trustworthy source/version policy for any dependency it offers to retrieve automatically.

Do not simply download arbitrary "latest" builds.

---

## Python runtime packaging

Determine the best relationship between:

```text
Electron installer
Python backend/runtime
post-install Python dependencies
```

through a packaging proof-of-concept.

---

## Detection review timing

The data architecture should support review.

Whether the complete review interface ships in the very first Phase 1 UI milestone or immediately after Queue/Settings remains a scope-management decision.

---

# 84. Important Superseded Decisions

The following earlier ideas should no longer drive implementation.

## React Native

Superseded by:

```text
Electron + React
```

---

## Commercial entitlement system

Deferred/removed from current scope.

---

## Mandatory bundled FFmpeg

Superseded by user-approved dependency retrieval/installation.

---

## Mandatory bundled Whisper model

Superseded by user-approved model retrieval.

---

## Stream-copy-only video as a licensing workaround

No longer a mandatory project limitation.

The user may choose:

```text
H.264
or
Preserve Source
```

because the application does not plan to distribute its own FFmpeg binary.

---

## Single-file-only Phase 1 frontend

Superseded by the current folder-driven batch model.

Phase 1 Queue shows all discovered files in the configured Ready directory.

Processing remains serial.

---

## Large multi-page frontend

Not required.

Current top-level scope:

```text
Queue
Settings
```

---

# 85. Architectural Guardrails

Do not:

```text
rewrite ProfanityCensor without demonstrated need
duplicate profanity logic in React
hardcode user directories
scrape console text as the final application API
process multiple jobs in parallel by default
modify source media in place
archive source on failure/cancel
silently install dependencies
silently change user output settings
assume FFmpeg capabilities
assume CUDA
bundle random development-machine binaries
turn the project into a generic video editor
```

---

# 86. Guiding Principle

When choosing between rebuilding a proven processing component and adapting the application around it:

> **Adapt the application around the proven engine unless a specific technical requirement demonstrates that the engine must change.**

The desktop project exists primarily to expose and orchestrate capabilities that already work:

```text
transcription
profanity detection
censorship
batch processing
```

while adding the things the CLI lacks:

```text
visible file state
configuration
directories
progress
cancellation
dependency setup
audio/video preferences
review capability
desktop packaging
usable distribution
```

---

# 87. Target End-State

The intended result is a public, portfolio-quality Windows desktop application that a normal user can download and operate without manually understanding the underlying Python project.

Conceptually:

```text
User downloads Profanity Censor
        ↓
installs application
        ↓
first-run dependency check
        ↓
user approves required FFmpeg/Whisper setup
        ↓
application verifies dependencies
        ↓
user chooses directories/settings
        ↓
Queue shows media in Ready
        ↓
user starts batch
        ↓
Transcribing
        ↓
Transcribed
        ↓
Censoring when enabled
        ↓
Finished
```

The repository should simultaneously demonstrate a coherent real-world architecture:

```text
Electron + React
        ↓
structured local service contract
        ↓
Python job/configuration layer
        ↓
proven censorship engine
        ↓
user-installed faster-whisper + FFmpeg
```

That is the current master direction for the Profanity Censor project.