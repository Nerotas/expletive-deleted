# Python backend module guide

The backend owns processing policy, settings, dependency readiness, jobs, and media safety. Electron starts `python -m scripts.desktop_bridge`; that module is a compatibility entrypoint for `backend.desktop.protocol`.

| Package/module | Responsibility |
| --- | --- |
| `desktop/bridge.py` | Compose the service and feature controllers; route private requests. |
| `desktop/protocol.py` | JSON-lines framing, concurrent dispatch, UTF-8 streams, process containment. |
| `desktop/installation.py` | Approved setup plans, workers, cancellation, status, and located components. |
| `policy/transactions.py`, `filesystem/locking.py` | Complete policy transactions, shared reentrant OS/thread ownership, and validated local redo recovery before snapshots. |
| `desktop/dictionary.py` | Dictionary pagination and transcript-review responses. |
| `desktop/native_files.py`, `service/outputs.py` | Main-only picker transactions, verified playback, expiring file leases, and guarded dictionary exports. |
| `service/` | Application lifecycle, library/archive operations, and capabilities. |
| `jobs/` | Job records/events, scheduling, local processing/copy workers, YouTube downloads, and batch CLI compatibility. |
| `censor/engine.py` | Coordinate transcription, detection, and media rendering for one source. |
| `censor/transcripts.py` | Validate, persist, and check cached transcripts. |
| `censor/media.py` | Probe audio layouts and recognize supported center-channel configurations. |
| `censor/detection.py` | Isolated vendor-dictionary review. |
| `censor/ffmpeg.py` | Run FFmpeg and translate progress; own processing-cancellation errors. |
| `censor/cli.py` | Advanced single-file command-line arguments and presentation. |
| `runtime/dependency_specs.py` | Supported component versions and download/package identities. |
| `runtime/dependency_models.py`, `dependency_errors.py` | Immutable setup contracts and shared errors. |
| `runtime/dependency_inspection.py` | Read-only component/model readiness checks. |
| `runtime/dependency_plan.py` | Build and identify inspectable setup plans without executing them. |
| `runtime/dependency_install.py` | Execute approved commands and verify their results. |
| `runtime/locations.py`, `paths.py` | Configured locations, executable resolution, and compatibility path helpers. |
| `runtime/devices.py`, `encoders.py`, `timing.py` | CPU/CUDA selection, video encoder probes, and local timing estimates. |
| `runtime/transcription.py`, `python_imports.py` | Optional speech-library adapter and isolated package import checks. |
| `settings/` | Typed settings, validation/serialization, atomic INI persistence, directory checks. |
| `policy/` | Durable user dictionary and factory defaults. |
| `application_identity.py`, `process_lifetime.py` | Application storage identity and Windows descendant ownership. |

`runtime/dependencies.py` and `runtime/environment.py` preserve established imports. They re-export implementations rather than maintaining duplicate behavior. Existing root CLI/module aliases and public censor imports remain available. New implementation code should use the owning module when it needs a specific responsibility.

Keep domain code independent of `scripts/` and root entrypoints. Transcript-only callers can import `censor.transcripts` without loading the processing engine. Optional processing packages must be imported only when required: startup and setup discovery need to work with private Python's standard library alone. The first CPU/CUDA capability request may load CTranslate2 after approved setup; importing the backend does not.

Add short comments for invariants such as approval binding, atomic publication, subprocess pipe handling, lock ownership, cancellation ordering, and Windows-specific behavior. Avoid comments that merely repeat a function name or assignment. Tests should patch dependencies where the implementation uses them, not a compatibility export.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_backend_architecture
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The architecture tests cover standard-library-only imports, transcript-module isolation, dependency direction, UTF-8 transcript reads, and setup cleanup after a service-close failure. Native Electron and packaged smoke remain necessary when module moves affect the bridge entrypoint or packaged resources.

See [the backend review](../docs/PYTHON_BACKEND_REVIEW_2026-09-16.md) for the inspection results and remaining behavioral risks. Module separation alone does not resolve concurrency, media-safety, or security defects.

## Dictionary transactions

Every managed policy read and mutation uses the permanent `.policy.lock` in the resolved dictionary directory. Lock order is service lifecycle, settings, policy, then destination ownership; never acquire settings while holding policy ownership. Release policy ownership before processing or network work. Snapshots used by jobs remain immutable for that job.

The transaction stages writes in memory, validates the intended split stores, flushes and atomically publishes `.policy-journal.json`, publishes stores, and removes the journal before acknowledging success. Recovery validates fixed store names and every payload before writing. Targeted reads still work independently of an unrelated corrupt store when no recovery is pending. Journal contents are local sensitive data and must not enter logs or CI artifacts.

Import and restore remain explicit whole-policy replacements at their serialized position; subsequent acknowledged edits survive. Imports retain the established imported-source/new-import-time behavior. Untouched entries and recovered journal entries retain their exact metadata. Earlier versions do not understand the lock/journal and must not share this profile concurrently.

The developer CLI uses the same policy transaction without starting a service:

```powershell
.\.venv\Scripts\python.exe backend_app.py dictionary add censor "example word"
.\.venv\Scripts\python.exe backend_app.py dictionary remove censor "example word"
.\.venv\Scripts\python.exe -m unittest tests.test_policy_transactions
```
