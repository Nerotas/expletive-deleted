# Python backend inspection and modularization — 2026-09-16

## Postmortem

The backend had sensible package names, but large files mixed setup contracts, dependency checks, installation, hardware discovery, transcript storage, processing, and CLI presentation. The desktop entrypoint also owned feature state. This made changes harder to isolate and encouraged tests to patch broad compatibility modules.

Those responsibilities now have focused modules with stable public exports. Inline comments explain important safety and lifecycle rules. Two small correctness improvements accompany the refactor: cached transcripts explicitly use UTF-8, and bridge shutdown waits for setup cleanup even if service cleanup raises. Optional native speech packages are now loaded on capability demand rather than backend import.

This is a structural improvement with targeted fixes, not a claim that every backend defect is resolved. The remaining risks below need separate behavior changes and regression coverage.

## Inspection scope

The inspection covered all 31 original Python files under `backend/`, the desktop entrypoint, compatibility imports, and their tests/callers. It examined responsibilities, import direction, optional dependency loading, settings and policy persistence, job lifecycle, media path construction, dependency consent, model use, and cancellation. The resulting backend has 51 Python modules, grouped by responsibility rather than a target line count.

| Area | Assessment and action |
| --- | --- |
| Settings | Already separated into models, serialization, persistence, directory checks, and resolution. Retained that structure; documented atomic publication. |
| Policy | Cohesive persistence module with structured entries and atomic individual writes. Added a note distinguishing file atomicity from transaction serialization; concurrent policy safety remains open. |
| Service | Appropriate application boundary with separate library/capability readers. Existing submission/settings lifecycle gate retained. Archive transactions need follow-up. |
| Jobs | Scheduling, records, events, artifact naming, and execution are already separate. Preserved those boundaries and clarified compatibility imports. Batch and download publication still differ from desktop censorship. |
| Censoring | Split transcript validation/persistence, audio metadata, vendor review, FFmpeg execution, and CLI presentation out of the processing coordinator. Kept class/public APIs compatible. |
| Dependency setup | Split specifications, immutable models, errors, read-only inspection, approval plans, and execution. Old dependency module is now an export facade. |
| Runtime environment | Split paths/resolution, CPU/CUDA selection, encoders, and timing estimates. Old environment module is now an export facade. |
| Desktop backend | Added feature controllers and separate transport; `scripts/desktop_bridge.py` is a thin entrypoint. Python method names and response shapes remain unchanged. |
| Windows lifecycle | Retained the tested Job Object containment and graceful/forced shutdown behavior. Cleanup ordering is now explained at the composition boundary. |

Examples of responsibility reduction: `runtime/dependencies.py` previously contained 848 lines of implementation; its largest extracted implementation module is about 304 lines. `runtime/environment.py` previously had 623 lines; paths/resolution is about 368 lines. The 571-line desktop script is now a 12-line entrypoint. `censor/engine.py` fell from 1,295 to approximately 925 lines; it remains the largest coordinator because it owns the processing sequence and rendering choices.

The refactor preserves function bodies wherever practical. An AST comparison against the original checked every top-level function/class moved from the three largest modules and the bridge: differences were limited to the UTF-8 cache read, shared progress formatting, the engine's extracted helpers/CLI adapter, and the composed desktop bridge. Model/version requirements, install commands, media filters, and transcription options were not changed.

See [backend/README.md](../backend/README.md) for the module map and extension rules.

## Comments and compatibility

Added or retained short rationale comments around exact-plan approval, flushed/atomic transcript and settings publication, stderr pipe handling, lazy optional imports, native process containment, and shutdown sequencing. Compatibility facades explain why they exist. Tests now patch each implementation's dependencies rather than relying on a moved function's old module globals.

The root compatibility entrypoints and `scripts.desktop_bridge` exports still work. Transcript-only imports do not load the censor engine. Standard-library-only imports remain supported for consent-driven first-run setup. No third-party dependency, bundled payload, or renderer API was added.

## Remaining findings

**2026-09-23 follow-up:** the dictionary portion of finding 4 is addressed by [HP-03 transactions and recovery](HP-03_IMPLEMENTATION_2026-09-23.md), with native single-instance and concurrent CLI validation. The setup/settings portion remains open. The findings below retain the original inspection context.

These findings are not fixed by moving code. Some were established in the preceding bridge assessment; others emerged from this backend-wide review.

1. **High: artifact names can collide for different sources with the same stem.** `jobs/media.py` generates the same transcript and video-output names for `movie.mp4` and `movie.mkv` in the same input directory. A temporary-path probe confirmed both collisions. Transcript compatibility checks validate schema/model/channels, but do not bind a cache to source identity or content. A robust fix needs a source identity scheme and explicit migration of existing artifacts.
2. **High: file publication safeguards are inconsistent across entrypoints.** Desktop censorship stages and verifies output; `jobs/batch.py:process_file` passes the final destination directly to the engine, including overwrite mode. Failed batch processing can therefore damage an existing output or leave an incomplete destination. Copy/import and YouTube publication also use a separate existence check followed by replacement, leaving a collision race. These are source-derived findings; this review did not process or overwrite real media.
3. **High: destination containment needs strengthening.** Source-relative checks exist, but output/archive/transcript paths are assembled without consistently resolving and validating destination parents against their configured roots. Directory aliases, symlinks, or Windows junctions require dedicated containment tests. No junction escape was executed during this review.
4. **High: dictionary and setup settings changes still have transaction races.** Atomic file replacement does not protect a read–modify–write sequence or multiple dictionary files. Setup still saves a complete settings snapshot after changing runtime fields. The earlier deterministic probes demonstrated lost dictionary edits and newer settings being overwritten; the feature extraction deliberately preserves these behaviors for focused follow-up fixes.
5. **Medium: configured roots may be nested.** Directory validation rejects identical normalized paths, but allows Finished beneath Ready. A temporary-path probe confirmed acceptance. Recursive scanning may then treat generated or archived media as new input. Define and validate allowed root relationships, including resolved aliases.
6. **Medium: cancellation and subprocess bounds are uneven.** YouTube metadata lookup and some hardware/media probes have no explicit timeout. FFmpeg processing checks cancellation while consuming progress lines, so a silent process can delay an in-app cancellation. Desktop exit still has its verified forced fallback, but that does not make every individual operation promptly cancellable.
7. **Medium: bridge recovery and operation ownership remain incomplete.** Archiving can race with submission; setup can schedule duplicate installers; setup completion uses mutable settings context; malformed protocol responses, polling recovery, and unbounded histories/diagnostics need the repairs identified in the preceding bridge assessment. Their Python owners are now `desktop/`, `service/`, and the focused runtime modules.
8. **Maintenance: rendering/transcription orchestration remains substantial.** The engine, batch CLI, download manager, and policy store are still sizable. Further extraction should follow independently testable responsibilities and shared safety rules, not arbitrary file-size limits. In particular, a shared verified-publication service would address a real divergence between desktop and CLI behavior.

The Electron sender/path authorization findings from the preceding bridge assessment remain outside this Python modularization change. The previous audit report/probes were already present as uncommitted work and are not part of these authorized refactor commits.

## Validation

- Full backend suite: **271 tests passed** (the original 266 plus five architecture/cleanup/encoding regressions).
- Focused runtime/processing suite: 107 passed; focused dependency/desktop suite: 48 passed during extraction.
- Native Electron smoke passed, including startup through the compatibility bridge entrypoint.
- Native graceful and forced shutdown smoke both passed.
- A separate unpacked Windows x64 package was built at `frontend/release/backend-modularity-verified/win-unpacked` without publishing or replacing earlier audit artifacts.
- Packaged first-run smoke passed with private Python. The package dependency/runtime audit passed before and after launch.
- Every packaged backend module imported successfully with the private interpreter in isolated, no-site-packages, no-bytecode mode.
- Whitespace validation passed. Renderer code/protocol contracts were unchanged; the frontend unit suite was not rerun for this Python refactor.

Native tests use synthetic media and controlled workers; they do not establish large-v3 accuracy or real codec/GPU behavior. No processing component/model download, installer execution, user-media operation, release publication, or push was performed. The local unpacked package is a validation artifact, not a release approval.

## Follow-up order

Unify verified output publication and destination containment first. Then bind artifacts to their source, make dictionary/settings/archive operations transactional, and make subprocess cancellation and bridge recovery consistent. Keep each behavior change separately reviewable with a regression that reproduces the underlying failure.
