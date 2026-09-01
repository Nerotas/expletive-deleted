# AGENTS.md

This file applies to the entire repository. It describes the product intent and the engineering standards that should guide changes made by people or coding agents.

## Product mission

Build a friendly desktop application that lets people submit audio or video, identify language they do not want included, and create a censored copy they can comfortably share with their family.

The presumed customer is a parent, not a media-processing expert. They want control over the content their children receive without needing to understand Python, FFmpeg, Whisper, codecs, shells, or model caches.

When priorities compete, use this order:

1. Protect the user's original media and privacy.
2. Make the end-user workflow clear, trustworthy, and recoverable.
3. Produce accurate, predictable censoring behavior.
4. Keep development modular, typed, testable, and easy to onboard into.
5. Optimize performance without weakening the priorities above.

## Product principles

- The normal experience is the Electron desktop application. End users should not need a terminal or a separately started backend.
- Processing is local by default. Do not upload media, transcripts, dictionary entries, or usage data without an explicit product decision and clear user consent.
- The user owns the content policy. Preserve their configured censor list, exclusions, processing method, timing, and output preferences exactly.
- Never imply that automated transcription or censorship is perfect. Make limitations, failures, and review opportunities understandable.
- Prefer plain language in the UI. Translate technical failures into an actionable explanation while retaining useful diagnostic detail for developers.
- Accessibility is part of usability: use semantic controls, keyboard support, visible focus, useful labels, and sufficient contrast.

## Media safety rules

- Never overwrite or delete source media silently.
- Keep originals by default. Archiving is opt-in and may occur only after output has been written and verified successfully.
- Failed or cancelled jobs must leave the source intact and remove incomplete output when safe.
- Resolve and validate paths before file operations. Reject paths outside configured roots, symlink escapes, unsupported inputs, and destination collisions.
- Preserve relative directories for recursive input so identically named files do not collide.
- Keep report-only processing available as a safe review-first workflow.
- Treat transcripts and detected words as potentially sensitive user data. Keep them local and avoid unnecessary content logging.

## Required dependencies and first-run setup

The processing workflow requires Python, required Python packages, FFmpeg/FFprobe, and the supported Whisper model. These third-party components are not distributed with the application. The customer is responsible for obtaining and installing them on their system.

The desktop application must make this setup process as easy as practical without bundling or redistributing those components.

- Detect missing, incompatible, or unverified components automatically.
- Explain what each component does, why it is required, approximate download/disk impact when known, and what action the user needs to take.
- Provide clear in-app guidance for obtaining supported versions from approved sources.
- Where appropriate, the application may open an official download location or provide exact installation instructions, but the user must remain in control of the download and installation.
- Do not silently download, install, bundle, redistribute, or modify third-party components.
- Verify components after installation and clearly show what remains missing or incompatible.
- Make failures retryable and actionable. Preserve valid existing installations and completed model downloads whenever possible.
- Do not report the system as ready until Python, required Python packages, FFmpeg, FFprobe, and the supported Whisper model have been verified.
- Keep dependency detection, validation, and setup guidance shared between the desktop and CLI workflows where practical.
- Do not change the dependency distribution model without an explicit product decision and a licensing review.

The current accuracy baseline is `faster-whisper` with `large-v3`. A change to supported models or the accuracy contract is a product/backend decision, not a renderer-only change.

## Architecture boundaries

### Python backend

- `backend/` is the source of truth for settings validation, capabilities, dependency plans, media discovery, jobs, events, transcription, censoring, and filesystem safety.
- Keep root Python commands as thin compatibility entrypoints. New backend code should import package modules rather than root wrappers.
- Backend operations should return structured results and actionable errors. Do not make the renderer parse human-formatted CLI output.
- Keep the Electron bridge protocol private, narrow, and validated. Changes to protocol names or payloads must update the typed renderer client and relevant tests together.

### Electron boundary

- Electron owns the native window, lifecycle, context-isolated preload API, directory picker, and Python child-process bridge.
- Keep `contextIsolation` enabled and `nodeIntegration` disabled in the renderer.
- Do not expose arbitrary filesystem, process, or shell access through preload.
- Do not build shell command strings from user input. Pass validated arguments through structured APIs.

### React renderer

- `frontend/src/App.tsx` composes the shell, navigation, global notifications, setup state, and feature routes. It should not become the owner of every feature.
- Feature code belongs under `frontend/src/features/`; shared controls belong under `frontend/src/components/ui/`; reusable hooks, types, utilities, and services belong in their named directories.
- Components must use `frontend/src/services/desktop-client.ts`. Raw backend method-name strings belong only at that typed boundary.
- Use React Router for page navigation, TanStack Query for backend/server state, and React Hook Form for settings drafts unless a deliberate architecture change is justified.
- Prefer hooks, composition, and focused components. Add an HOC only when a real cross-cutting wrapper concern exists.
- Preserve the established visual language unless a task explicitly calls for redesign.

## Settings behavior

- User settings live outside the repository in the platform application-data directory. On Windows the default is `%LOCALAPPDATA%\ExpletiveDeleted\settings.ini`.
- `config.example.ini` documents the schema; generated `settings.ini` and machine-specific paths must remain ignored by Git.
- Writes must be validated and atomic. Preserve compatible settings across upgrades and make migrations explicit.
- The renderer maintains separate persisted and draft snapshots. Editing a field must not save automatically or be overwritten by background polling.
- Save the complete validated draft. On failure, retain edits and display the backend error. Discard restores the last persisted snapshot without reloading Electron.
- Queue polling may refresh library, jobs, and events only; it must not reload settings.

## Developer experience

- Windows is the current desktop target. Keep portable backend behavior where practical, but verify Windows paths and the native Electron runtime.
- Required frontend runtime: Node.js 22.12 or later.
- Required backend runtime: Python 3.9 or later in the repository-local `.venv`.
- `npm run dev` from `frontend/` should start the complete development application, including the private Python bridge. Do not require a routine second terminal.
- Keep setup, diagnostics, errors, and documentation consistent. If a workaround is repeatedly needed, improve the tooling instead of relying only on tribal knowledge.
- Add dependencies only when they materially reduce complexity, improve safety, or provide well-maintained behavior.
- Keep source and configuration files tracked. Never globally ignore `*.ts`, `*.tsx`, `*.d.ts`, or essential build/test configuration files to avoid media-extension collisions.
- Keep generated output, caches, downloaded models, local settings, machine paths, user media, and secrets out of Git.
- Preserve unrelated worktree changes and existing line-ending conventions. Avoid broad mechanical rewrites during focused work.

## Validation

Use validation proportional to the change. Do not claim completion without reporting what ran and any relevant limitation.

Backend validation from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Frontend validation from `frontend/`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
npm run smoke
```

- Run focused tests during development and the full relevant suite before handoff.
- Add regression coverage for fixed bugs, especially media safety, settings persistence, background polling, dependency readiness, IPC contracts, and cancellation/error recovery.
- Use the native Electron smoke test for preload, routing, backend startup, and important theme/accessibility integration.
- Visually inspect meaningful UI changes in both light and dark modes at supported window sizes.

## Documentation and handoff

- Keep `README.md`, `QUICKSTART.md`, `TROUBLESHOOTING.md`, `PROJECT_SUMMARY.md`, and `frontend/README.md` aligned with actual behavior.
- Write end-user instructions for a parent using the desktop application first. Put CLI and backend details in clearly marked advanced/developer sections.
- State whether operations download files, install software, move media, overwrite output, or require network access before asking the user to proceed.
- In handoffs, lead with the user-visible outcome, then summarize architecture changes, validation performed, and any remaining risk.

## Definition of done

A change is done when it improves or preserves the parent-facing workflow, respects media and privacy safeguards, keeps required dependencies understandable and obtainable, follows the architecture boundaries above, includes appropriate tests, passes relevant validation, and leaves documentation accurate.

## Git and repository safety

Coding agents may inspect the repository, modify files in the working tree, run tests, and report proposed changes without additional permission.

Repository history and remote repositories require explicit user authorization.

- Do not create a Git commit unless the user explicitly asks for a commit.
- Do not push commits or branches to any remote unless the user explicitly asks for a push.
- Permission to modify files does not imply permission to commit.
- Permission to commit does not imply permission to push.
- Do not create or push tags without explicit permission.
- Do not amend commits, rebase branches, reset history, force-push, delete branches, or perform other history-rewriting/destructive Git operations without explicit permission for that specific operation.
- Do not discard, overwrite, clean, stash, or otherwise remove unrelated worktree changes unless explicitly instructed.
- Before an authorized commit, report the files being committed and the validation performed.
- Before an authorized push, report the branch and remote that will receive the changes.