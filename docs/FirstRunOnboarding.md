# First-Run Onboarding Workflow

## Purpose

Create a first-open workflow that guides a new user through preparing Expletive Deleted and completing their first media workflow without requiring knowledge of Python, FFmpeg, Whisper, models, or application-data files.

The onboarding state may be represented by a validated flag in `settings.ini`:

```ini
[onboarding]
completed = false
```

The final onboarding step sets `completed = true`. This flag records only whether the walkthrough was completed. Dependency readiness must continue to come from live backend capability checks.

## Product Goals

- Explain required third-party components in plain language.
- Keep every download and installation under explicit user control.
- Initialize a useful censored-word dictionary without distributing a personal exclusions list.
- Help the user choose an appropriate censoring method.
- Let the user accept or change all working directories.
- Teach the Ready-folder and drag-and-drop workflows.
- Explain the difference between transcription and censored transcoding.
- Preserve original media and local privacy throughout setup.

## Open Behavior

Open onboarding when settings are first created or `onboarding.completed` is `false`.

- Save progress after each completed step so setup is resumable.
- Closing the window preserves progress and opens onboarding again on the next launch.
- Do not mark onboarding complete merely because dependencies are ready.
- Provide a way to reopen onboarding from Help or Settings after completion.
- Never download or install third-party components without explicit approval.
- Never upload, move, overwrite, or delete source media during onboarding.
- Continue checking capabilities on every launch, even after onboarding is complete.

Suggested flow:

```text
Welcome
  -> Prepare components
  -> Prepare dictionary
  -> Choose censoring method
  -> Confirm folders
  -> Learn how to add media
  -> Learn how to process media
  -> Finish
```

## Step 1: Welcome

Explain that:

- Processing occurs locally by default.
- Media and transcripts are not uploaded.
- Automated transcription and censorship are not perfect.
- Original files are retained by default.
- Finished media should be reviewed before it is shared.

Show a short summary of the steps the user will complete. Do not present technical configuration details on this screen.

## Step 2: Prepare Required Components

Check and present each required component independently.

### FFmpeg and FFprobe

Explain that FFmpeg and FFprobe inspect media and create the censored output file.

### faster-whisper and Python packages

Explain that `faster-whisper` and its required Python packages transcribe spoken language locally. Use the product term **Speech recognition** in prominent UI copy and retain package names in supporting details.

### Whisper large-v3 model

Explain that the Whisper `large-v3` model supplies the supported accuracy baseline for word recognition and timing. The model is separate from the speech-recognition software and requires a substantial download and disk space.

For every component:

- Show `Checking`, `Ready`, `Missing`, `Invalid`, or `Incompatible` state.
- Offer **Locate existing** where supported.
- Offer **Get** only through the existing reviewed install-plan workflow.
- Before retrieval, show the source, expected action, approximate download size when known, destination, and disk impact.
- Require explicit approval before beginning.
- Verify the component after installation or selection.
- Preserve valid existing installations and completed model downloads.
- Make failures actionable and retryable.

Keep **Continue** disabled until Python packages, FFmpeg, FFprobe, and the supported Whisper model are verified.

Do not bundle these processing components or silently download them.

## Step 3: Prepare the Dictionary

Offer two choices:

- **Use default censored words**
- **Import a dictionary**

Using defaults initializes the live `dictionary\censored.json` store from the bundled censored-word resource.

The application should not distribute a developer's personal exclusions. The shipped `resources\profanity_exclusions.txt` file should remain available to preserve independent store initialization and overlap validation, but its release content may be empty. Personal exclusions belong only in the user's local:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\exclusions.json
```

The onboarding workflow must not copy a developer workstation's local exclusions into application resources or packaged artifacts.

The live stores remain:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\censored.json
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\exclusions.json
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\discovered.json
```

Combined dictionary JSON remains only the explicit import/export format. Imported dictionaries must be validated before replacing live state, and failed imports must leave the current dictionary untouched.

## Step 4: Choose a Censoring Method

Use a segmented choice with concise explanations. An audio preview may be added later but is not required for the initial implementation.

### Drop audio

Silence the complete audio mix during every detected interval.

- Most predictable option.
- Works with mono and stereo audio.
- Removes dialogue, music, and sound effects during the interval.
- Recommended when reliably obscuring the detected word matters most.

Persist as:

```ini
[censoring]
stereo_method = drop_audio
```

### Karaoke

Use stereo channel cancellation during every detected interval.

- Attempts to remove centered dialogue while retaining some music and effects.
- Can sound less abrupt than total silence when the source mix is suitable.
- Results depend on how the source audio was mixed.
- May not remove off-center speech completely.
- Is not appropriate for mono audio.

Persist as:

```ini
[censoring]
stereo_method = karaoke
```

Default to **Drop audio**. State clearly that neither method guarantees perfect censorship and that finished output should be reviewed.

Surround handling remains governed by the existing surround-output setting and backend behavior; onboarding must not replace or bypass it.

## Step 5: Confirm Working Folders

Show the validated defaults:

```text
%USERPROFILE%\Documents\Expletive Deleted\Ready
%USERPROFILE%\Documents\Expletive Deleted\Finished
%USERPROFILE%\Documents\Expletive Deleted\Processed
%USERPROFILE%\Documents\Expletive Deleted\Transcripts
```

Explain each directory:

- **Ready / Input** contains media waiting to be processed.
- **Finished / Output** receives censored copies.
- **Processed / Archive** optionally stores originals after verified success.
- **Transcripts** stores reusable local transcripts.

Allow each directory to be changed independently using the existing native directory picker.

Before continuing:

- Require absolute, distinct paths.
- Resolve and validate paths through the backend.
- Show whether each directory exists and is writable.
- Ask before creating missing directories.
- Reject unsupported paths, symlink escapes, and destination collisions.
- Do not enable automatic source archival unless the user deliberately chooses it.

Saving onboarding directory choices must use the same complete, validated, atomic settings update as the Settings page.

## Step 6: Add Media

Explain the two current ways to add media.

### Ready folder

The user may place supported audio or video files directly into the configured **Ready / Input** folder. The Queue reads supported files from that location and, when enabled, its subdirectories.

### Drag and drop

The user may drag media files into the Queue. Before copying, show the existing confirmation dialog and explain that:

- Files are copied into Ready.
- Original files remain in their current locations.
- Adding files does not automatically start processing.
- Unsupported files and destination collisions are rejected safely.

Adding an entire external folder through an import picker is not currently implemented. If folder import is added as part of this task, it must preserve relative paths, avoid filename collisions, reject unsupported inputs and symlink escapes, and retain all originals. Otherwise, onboarding should describe placing a folder beneath Ready when subdirectory scanning is enabled.

## Step 7: Transcribe and Censor

Explain the review-first workflow:

1. Choose **Transcribe only** to create and verify a transcript without creating media output.
2. Review discovered words in **Dictionary** and classify them as **Censor** or **Ignore** when appropriate.
3. Choose **Transcribe + Transcode** to create a censored copy. A compatible verified transcript may be reused.
4. Review the finished file before sharing it.

Also explain:

- Jobs run one at a time in queue order.
- Transcoding cannot begin until a compatible transcript has been persisted and verified.
- **Retranscribe** replaces an existing transcript while retaining finished media.
- **Retranscode** reuses a compatible transcript and replaces finished output only after the new output succeeds.
- Originals remain in Ready unless the user explicitly archives them or enables success-only archival.
- Failed or cancelled jobs retain the original and remove incomplete output when safe.

The walkthrough may use annotated UI states, but it must not require processing real media before onboarding can be completed.

## Step 8: Finish

Show a summary of the selected and verified state:

- Required components verified.
- Default censored words initialized or a dictionary imported.
- Censoring method selected.
- Working folders validated.
- Source archival preference displayed.

Selecting **Finish setup** atomically saves:

```ini
[onboarding]
completed = true
```

Then navigate to Queue.

Do not treat the completion flag as evidence that dependencies remain ready. If a component is later removed or becomes incompatible, the normal capability UI must show setup as required and processing must remain disabled.

## Settings Schema

Add a focused settings group:

```python
@dataclass(frozen=True)
class OnboardingSettings:
    completed: bool = False
```

Add `onboarding` to:

- `AppSettings`
- Settings validation
- Dictionary/INI serialization
- The complete settings update contract
- Renderer settings types
- Test fixtures
- `config.example.ini`

Suggested INI schema:

```ini
[onboarding]
completed = false
```

If individual step progress is persisted, use a validated explicit step identifier rather than several loosely related booleans. The only required flag for the initial implementation is `completed`.

Because the settings schema currently rejects unknown groups and fields, this change must update backend parsing, serialization, frontend types, and tests together.

## Architecture Boundaries

- The backend remains the source of truth for settings, dependency capabilities, install plans, dictionary persistence, directory validation, and media safety.
- The renderer owns presentation and temporary wizard navigation state.
- Use the typed desktop client; do not add raw backend method strings outside that boundary.
- Reuse existing dependency, settings, dictionary, directory-picker, and media-import operations where practical.
- Do not duplicate capability state in settings.
- Do not expose filesystem or process access through preload.
- Preserve `contextIsolation`, disabled renderer `nodeIntegration`, and the narrow preload API.

## Error and Recovery Behavior

- A failed step retains all previously saved valid choices.
- Closing onboarding does not mark it complete.
- Dependency failures preserve completed downloads and valid installations.
- Dictionary initialization failures do not leave partial live stores.
- Settings save failures preserve the previous `settings.ini` and keep the current wizard choices visible.
- Directory failures identify the affected field and allow retry or reselection.
- The user may move backward without losing unsaved choices in the current session.
- The user may safely restart the application and resume onboarding.

## Test Coverage

### Backend

Add focused tests covering:

- Missing settings create `onboarding.completed = false`.
- The onboarding flag round-trips through INI serialization.
- Invalid onboarding values are rejected.
- Completing onboarding is written atomically.
- A failed save preserves the previous INI.
- Default censored-word initialization does not import personal exclusions.
- Empty bundled exclusions initialize a valid independent exclusions store.
- Dependency readiness remains capability-derived after onboarding completion.

### Renderer

Add tests covering:

- Fresh settings open onboarding.
- Completed settings open the normal Queue.
- Closing incomplete onboarding causes it to reopen on the next launch.
- Required dependency states and consent actions are shown.
- Continue remains disabled until all required components verify successfully.
- Dictionary defaults and import are distinct choices.
- Drop audio and Karaoke explanations are visible and the selection persists.
- Default directories are shown and may be changed independently.
- The Ready-folder and drag-and-drop instructions are present.
- Transcribe-only and Transcribe-plus-Transcode instructions are present.
- Finish saves the complete settings draft with `completed = true` and navigates to Queue.
- Capability failure still blocks processing after onboarding completion.

### Native Smoke

Extend Electron smoke coverage to confirm:

- A fresh temporary app-data directory opens onboarding.
- The preload remains context-isolated and narrowly typed.
- No dependency retrieval begins without confirmation.
- A completed onboarding flag opens Queue on a later launch.

Do not require network downloads or real media processing in automated smoke tests.

## Acceptance Criteria

1. Fresh settings open onboarding automatically.
2. Incomplete onboarding resumes after application restart.
3. Completed onboarding does not reopen automatically.
4. The walkthrough can be reopened deliberately from Help or Settings.
5. Dependencies require review and consent before retrieval.
6. Onboarding cannot report processing readiness until required components verify successfully.
7. Default censored words can be initialized without distributing personal exclusions.
8. Live censored, exclusions, and discovered stores remain independent.
9. Censoring choices include accurate plain-language tradeoffs.
10. Default folders can be accepted or changed independently.
11. Users learn both Ready-folder and drag-and-drop workflows.
12. Users learn the distinction between transcription and censored transcoding.
13. Completing onboarding persists the flag through the atomic settings path.
14. Capability failures remain visible after onboarding completion.
15. Originals are never moved, overwritten, uploaded, or deleted by onboarding.
16. Root Python compatibility entrypoints and transcript compatibility validation remain intact.
17. Relevant backend, renderer, build, and native smoke validation passes.

## Validation

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

From `frontend/`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
npm run smoke
```

Also verify manually in light and dark themes at supported desktop sizes:

- Fresh first-open flow.
- Resume after closing midway.
- Directory validation and retry behavior.
- Dependency consent and cancellation behavior.
- Final navigation to Queue.
- Reopening onboarding after completion.
