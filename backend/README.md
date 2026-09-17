# Python backend module guide

The backend owns processing policy, settings, dependency readiness, jobs, and media safety. Electron starts `python -m scripts.desktop_bridge`; that module is a compatibility entrypoint for `backend.desktop.protocol`.

| Package/module | Responsibility |
| --- | --- |
| `desktop/bridge.py` | Compose the service and feature controllers; route private requests. |
| `desktop/protocol.py` | JSON-lines framing, concurrent dispatch, UTF-8 streams, process containment. |
| `desktop/installation.py` | Approved setup plans, workers, cancellation, status, and located components. |
| `desktop/dictionary.py` | Dictionary pagination and transcript-review responses. |
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
