# High-priority issues and product decisions

Decision date: 2026-09-17  
Scope: Windows desktop application, Electron bridge, Python backend, and React frontend.

## Purpose and status

This is the first document from the consolidated review. It records the issues discussed with the product owner and the decisions reached, before preparing a separate implementation plan in the next phase.

The earlier reports contain nine distinct open high-priority issues after overlapping findings are consolidated. Eight have an accepted repair direction. Source identity, artifact naming, and legacy migration are deferred to a future issue. Two earlier Windows lifecycle findings were already resolved and are recorded separately below.

**Accepted decisions are not completed fixes.** This document does not implement repairs or newly reproduce the audit findings. Evidence and validation limits remain in the linked source reports. Detailed implementation choices, sequencing, regression tests, and release qualification belong in the second document.

Implementation updates are linked in the status table; the original decisions below remain the approved scope.

## Decision register

| ID | Issue | Decision | Status |
| --- | --- | --- | --- |
| HP-01 | Untrusted documents retain desktop bridge access | Restrict the app window to its own interface, validate every IPC caller, and open external links in the default browser | [Implemented; Windows/package checks passed](HP-01_IMPLEMENTATION_2026-09-17.md) |
| HP-02 | File opening and dictionary export accept unrestricted paths | Restrict playback to verified media within the configured output root; bind JSON exports and overwrite consent to the native Save dialog | [Implemented; Windows/package checks passed](HP-02_IMPLEMENTATION_2026-09-17.md) |
| HP-03 | Concurrent dictionary edits can lose acknowledged changes | Serialize complete dictionary changes and allow one desktop instance per user | Accepted direction; open |
| HP-04 | Component setup can overwrite newer settings | Update only verified component fields, preserve unrelated settings, and surface conflicts with manual path edits | Accepted direction; open |
| HP-05 | Artifact names collide and legacy transcripts lack reliable source identity | Retain as a future issue; defer the identity scheme and legacy migration decision | Deferred; risk remains open |
| HP-06 | Publication safeguards differ across processing entrypoints | Use shared staging, verification, and safe publication; stop on unexpected collisions | [Implemented; cross-volume hardware qualification remains](HP-06_IMPLEMENTATION_2026-09-17.md) |
| HP-07 | Destination links can escape configured roots | Allow a configured root to resolve elsewhere, enforce that resolved boundary, and stop on escapes or unexpected target changes | [Implemented Windows guards, including HP-06 integration](HP-07_IMPLEMENTATION_2026-09-17.md) |
| HP-08 | Setup progress hides communication failures | Provide serialized polling and a visible 30-second reconnection phase, followed by explicit recovery when necessary | Accepted direction; open |
| HP-09 | Onboarding can save an obsolete settings snapshot | Save only intended wizard changes and progress; preserve newer settings and pause on same-field conflicts | Accepted direction; open |

## HP-01: Restrict privileged access to the application interface

**Problem:** an outside document loaded into the Electron window can retain access to privileged preload operations. Context isolation and disabled Node integration alone do not establish who may call the bridge.

**Agreed behavior:**

- Keep the application window limited to the app's trusted interface.
- Validate every IPC caller at the Electron boundary.
- Open external links in the user's default browser.
- Limit development-server access to development mode.

There is no requirement to display external websites inside the application window. Detailed sender/frame validation, navigation controls, sandboxing, and CSP implementation will be addressed in the later technical plan; renderer lint rules do not enforce this security boundary.

Source: [bridge assessment, B01](BRIDGE_ASSESSMENT_2026-09-16.md#b01--untrusted-navigation-retains-privileged-bridge-access).

## HP-02: Authorize playback and dictionary export destinations

**Problem:** the renderer can supply arbitrary paths for native file opening, including executable paths. Dictionary export can replace a destination without binding the request to a Save dialog selection and its overwrite confirmation.

**Agreed behavior:**

- In-app playback is restricted to verified media within the configured output folder, subject to the resolved-path safeguards in HP-07.
- Files moved elsewhere can be opened through Explorer. A “Locate moved file” feature is not included in this repair direction.
- Dictionary export uses the native Save dialog and an exact selected JSON destination.
- Replacing an existing JSON file requires explicit overwrite confirmation.
- The Save dialog may select any user-accessible folder; the output-root restriction applies to playback, not dictionary export.

The restriction trades convenience for a smaller, clearer native-access boundary. Authorization must be enforced beyond the renderer.

Source: [bridge assessment, B02](BRIDGE_ASSESSMENT_2026-09-16.md#b02--native-file-operations-accept-arbitrary-renderer-paths).

## HP-03: Preserve concurrent dictionary changes

**Problem:** overlapping dictionary updates can both report success while one overwrites the other's snapshot. Atomic replacement of individual files does not serialize a complete policy transaction.

**Agreed behavior:**

- Serialize complete dictionary changes so accepted edits are not silently lost.
- Allow one desktop instance per user. Launching the application again focuses the existing window.

Single-instance desktop ownership does not by itself protect against CLI access or background policy writers. The technical plan must account for those writers when defining transaction ownership and locking; a particular locking or storage mechanism has not been selected in this discussion.

Sources: [bridge assessment, B03](BRIDGE_ASSESSMENT_2026-09-16.md#b03--concurrent-dictionary-changes-lose-acknowledged-edits); [backend review, remaining finding 4](PYTHON_BACKEND_REVIEW_2026-09-16.md#remaining-findings).

## HP-04: Preserve settings when component setup completes

**Problem:** setup can read all settings, change a runtime field, then save that obsolete full snapshot after the user has saved newer preferences. This can undo onboarding progress or unrelated settings.

**Agreed behavior:**

- Setup updates only its verified component fields.
- Preserve unrelated preferences and progress saved in the meantime.
- If setup and the user changed the same runtime path, preserve the manual choice from automatic overwrite and surface the conflict for resolution.
- Do not silently choose between conflicting values.

This decision covers setup-originated writes. HP-09 addresses the opposite direction: an onboarding save overwriting newer setup results. Both must follow a consistent conflict policy.

Sources: [bridge assessment, B04](BRIDGE_ASSESSMENT_2026-09-16.md#b04--setup-completion-overwrites-newer-saved-settings); [backend review, remaining finding 4](PYTHON_BACKEND_REVIEW_2026-09-16.md#remaining-findings).

## HP-05: Source identity and legacy artifacts — deferred

**Problem:** different sources such as `movie.mp4` and `movie.mkv` can generate the same transcript and output names. Existing transcript compatibility checks do not reliably establish that a transcript belongs to the exact current source content.

**Decision:** retain this as a future issue. The product owner wants it addressed eventually but considers the naming, identity, processing-cost, and migration choices too substantial to settle in this phase. Deferral does not lower or resolve the risk.

**Constraints and discussion to preserve for that future issue:**

- Identification and migration must never alter the original media. Reading a file to identify it does not authorize renaming, moving, rewriting, or deleting it.
- Avoid unnecessary retranscription; existing transcription times are already a significant concern.
- Collision-resistant artifact names and content fingerprints were discussed as possible approaches, not a finalized implementation.
- Fingerprinting would read media without running the transcription model. Its cost depends on file sizes and storage; no timing estimate or benchmark was established.
- Legacy migration may mainly affect the product owner's existing collection and could be handled by a one-off tool.
- A preview-and-confirm migration that preserves transcripts and finished copies was discussed. A fingerprint captured today cannot prove which source originally produced an old transcript; a manually confirmed mapping would establish a trusted legacy baseline.
- Neither blanket regeneration nor a particular legacy-adoption policy was approved. The handling of ambiguous or incompatible legacy entries remains undecided.

The next implementation plan should retain this deferral explicitly. HP-06 can protect publication against collisions without treating the broader artifact-identity problem as solved.

Source: [backend review, remaining finding 1](PYTHON_BACKEND_REVIEW_2026-09-16.md#remaining-findings).

## HP-06: Preserve originals and existing outputs during publication

**Problem:** desktop censorship stages and verifies output, while batch processing can write directly to a final destination. Imports and downloads also have destination-collision races. Failure or cancellation can therefore damage an existing output or leave an incomplete destination in some workflows.

**Agreed behavior:**

- Apply shared staging, verification, and safe-publication rules across the affected workflows.
- Write new results to temporary files and verify them before publication.
- Preserve originals and existing finished files on failure or cancellation.
- Require explicit authorization to replace an existing output.
- Stop for a user decision when an unexpected destination collision occurs. Do not silently overwrite or automatically accumulate uniquely named copies.

Normal publication must not modify original source contents. Existing opt-in archival behavior remains subject to its established requirement for successful, verified output; this decision does not authorize additional source movement.

Source: [backend review, remaining finding 2](PYTHON_BACKEND_REVIEW_2026-09-16.md#remaining-findings).

## HP-07: Enforce resolved destination boundaries

**Problem:** a symlink or Windows junction beneath an output, archive, or transcript folder can redirect file operations outside the intended root.

**Agreed behavior:**

- Allow the configured root itself to resolve to another location, including another drive.
- Treat that resolved location as the permitted boundary.
- Reject destinations whose resolved paths escape that boundary, including through linked subfolders.
- Revalidate before writes and stop if the target changes unexpectedly.
- Report unavailable drives and invalid destinations with actionable feedback.

The product owner does not intentionally use symlinks, but accepted this balanced policy rather than rejecting all links. This decision does not establish support for every network filesystem or decide the separate medium-priority question of nested configured roots.

Source: [backend review, remaining finding 3](PYTHON_BACKEND_REVIEW_2026-09-16.md#remaining-findings).

## HP-08: Reconnect visibly before declaring communication failure

**Problem:** setup polling suppresses communication errors and permits overlapping requests. The UI can keep showing active work after contact with the backend is lost, or show out-of-order status.

**Agreed behavior:**

1. Poll serially and prevent stale responses from replacing newer state.
2. On loss of communication, show a visible reconnection phase with elapsed time. Retry status checks with increasing delays for up to **30 seconds**.
3. Do not resend installation commands during reconnection.
4. If contact returns, read the actual operation status and resume accurate feedback.
5. If reconnection fails, explain the problem and offer explicit recovery. Keep the installation outcome unknown until it can be verified; a communication failure does not prove installation failed or rolled back.
6. If the backend is known to have exited, show recovery guidance immediately rather than waiting through the reconnection window.
7. Recheck what completed after recovery, preserve valid downloads, and require an explicit Retry action to resume unfinished setup rather than automatically restarting installation.

The product owner explicitly required feedback and requested the reconnection phase before failure reporting. Automatic backend process restart, persistence of operation identities across restart, and the detailed retry schedule still need technical design; they were not independently selected here.

Sources: [frontend review, setup polling finding](FRONTEND_REVIEW_2026-09-16.md#remaining-findings-and-recommended-follow-up); [bridge assessment, B10](BRIDGE_ASSESSMENT_2026-09-16.md#b10--setup-polling-hides-loss-of-the-bridge). The earlier bridge report rated this medium; it is included here because the frontend review rated it high.

## HP-09: Preserve newer settings during onboarding

**Problem:** onboarding holds a settings snapshot across steps. A later wizard save can overwrite newly verified component paths or other settings changed after that snapshot was captured.

**Agreed behavior:**

- Save only the wizard's intended changes and onboarding progress.
- Preserve newer settings outside those changes, including verified component paths.
- If the same field changed in both places, retain the wizard's draft and present the conflict.
- Pause onboarding advancement until the user chooses which value to keep.
- Use the same conflict-handling policy as component setup in HP-04.

Source: [frontend review, onboarding snapshot finding](FRONTEND_REVIEW_2026-09-16.md#remaining-findings-and-recommended-follow-up).

## Previously resolved high-priority findings

| Finding | Recorded resolution | Remaining qualification |
| --- | --- | --- |
| Closing the app bypassed processing cleanup | Graceful bridge shutdown, bounded forced fallback, Windows process-tree containment, and staged desktop output publication | Existing tests used controlled workers; this does not establish real-media or clean-machine release qualification |
| Saving settings lost active download tracking | Settings replacement is blocked while downloads are active, and settings/submission operations share a lifecycle lock | Separate setup/onboarding settings races in HP-04 and HP-09 remain open |

Sources: [Windows build audit](WINDOWS_BUILD_AUDIT_2026-09-16.md); [Windows lifecycle follow-up](WINDOWS_LIFECYCLE_FOLLOWUP_2026-09-16.md). These resolved defects should retain their regression coverage rather than be reopened as unfinished repairs.

## Boundary for the next phase

The second document will turn the eight accepted directions into a repair plan and carry HP-05 as a deferred future issue. It should map shared work across frontend, bridge, and backend without counting the same settings or dictionary defect twice.

Other medium-priority findings, architecture improvements, and release-qualification gaps remain in their original reports. They have not all been individually decided in this discussion. If any is necessary to implement an accepted decision safely, the plan should identify that dependency explicitly rather than imply that it was already resolved or separately approved.
