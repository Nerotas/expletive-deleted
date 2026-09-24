# HP-04 implementation — 2026-09-24

## Result

Component setup and locating an existing component preserve newer preferences, onboarding progress, and unrelated runtime paths. Same-field conflicts publish no settings and offer explicit Keep current / Use verified choices. Completed component files remain available; resolution verifies selected existing components and never replays installation.

Onboarding uses the same backend transaction in the opposite direction, preserving paths applied by setup. Normal Settings submits a complete draft with its baseline. Wizard cancellation retains its draft and step; normal Settings preserves edits made while a save is pending.

## Implementation

- `backend/settings/transactions.py` defines typed snapshots, opaque canonical revisions, allowlisted field changes, and expected/current/proposed conflicts. Store transactions read current persisted state under the shared OS/thread lock, merge intended fields, and validate the entire result before atomic INI publication. Directory bindings and the INI schema remain compatible.
- Effective legacy directory overrides appear in snapshot revisions without being written into saved preferences. Editing an overridden field is rejected explicitly.
- The service keeps lifecycle ownership ahead of settings locking, rejects active jobs/downloads, and constructs replacement managers before publication. Construction, validation, flush, and persistence failures preserve usable prior managers and settings. Temporary INI files are removed on failed publication.
- The desktop acquires profile ownership before loading settings. Supported CLI writers, including bootstrap initialization, honor that ownership; read-only settings commands and dictionary transactions remain available.
- Each plan review has a distinct approval token and immutable baseline/model/destinations. Repeated approval of one token returns the same operation. Independent components merge safely; overlapping active setup is blocked. Only successful component fields are applied, including successful earlier actions when a later action fails.
- FFmpeg and FFprobe are verified/applied together at the approved destination. Model verification remains bound to the captured cache; a changed selected model requires verification for the newly selected model before using that cache.
- `awaiting_resolution` retains verified selections and exposes the latest snapshot. Resolution uses a strict fresh revision, so another change requires another choice. Keep current may leave a manual path unready; it does not depend on files belonging to a discarded verified selection. Readiness is checked separately.
- The typed desktop client, IPC allowlist, onboarding, Settings, and setup controllers share the new contracts. The conflict dialog traps/restores focus, supports keyboard choices, groups the FFmpeg pair, and uses plain field labels.

## Validation

Validated on Windows with repository Python 3.14.0 and Node.js 24.12.0:

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: **341 passed**.
- `npm test -- --run`: **160 passed** in 13 test files.
- `npm run typecheck`, `npm run lint`, and `npm run build`: passed.
- `npm run smoke`: passed with the native Electron preload, backend, and routing.
- `npm run smoke:state`: all seven mandatory scenarios passed.
- `node scripts/smoke-shutdown.mjs`: graceful and forced shutdown passed.
- `git diff --check`: passed.

Focused backend regressions cover both path choices, repeated conflicts, independent-process contention, active jobs/downloads, invalid merged values, overridden settings, directory swaps, failed manager construction, persistence/flush failure, and successful components retained after a later action fails. Renderer regressions cover draft/baseline separation, cancellation, repeat conflicts, late edits, duplicate saves, discard after conflict, paired choices, focus, and refreshing paths after partial setup failure.

The native state fixture replaces component verification/downloads with offline synthetic results. It exercises the real Electron main/preload, Python bridge, persistent settings transactions, concurrent requests, and renderer. Its required cases fail the script if omitted:

1. A second launch during startup creates no second bridge/window.
2. A second launch restores/focuses the original window.
3. Concurrent CLI and desktop dictionary edits survive.
4. Setup conflict resolution detects another change and retains a completed download without reinstalling.
5. Paused inspection preserves newer preferences and resolves the manual path conflict.
6. Wizard Back/Continue/Finish preserves paths and preferences changed between steps.
7. CLI settings writes are rejected while the desktop owns the profile.

Screenshots cover the conflict dialog in light/dark at 1060×720 and 1440×940; checked for readable wrapping and horizontal fit. Backend CI explicitly requires the settings/install-conflict suites. Existing frontend quality and native state gates enforce types, renderer tests, and the seven native scenarios; release and local release validation already invoke state smoke.

## Limits

No processing dependency was downloaded or installed for these checks, and no user media was processed. Synthetic verifier results do not qualify real codec/model/GPU combinations or live downloads. Pending setup review is session-local; retained files can be selected through Locate existing after a restart. This change does not implement durable installer resumption or close the broader HP-08 recovery work. The shared onboarding transaction is implemented, but this report does not independently close every HP-09 acceptance item.

No release workflow, remote push, installer publication, or live-site operation was performed. Older versions do not honor the new profile/settings locks and must not run concurrently against the same profile.

## Follow-up commit files

The initial implementation was already recorded in `2e47b84`. The follow-up preserves that history and completes validation and fixes in these files:

- `PROJECT_SUMMARY.md`
- `QUICKSTART.md`
- `README.md`
- `TROUBLESHOOTING.md`
- `backend/README.md`
- `backend/desktop/bridge.py`
- `backend/desktop/installation.py`
- `backend/service/application.py`
- `backend/settings/store.py`
- `backend/settings/transactions.py`
- `docs/HIGH_PRIORITY_ISSUES_AND_DECISIONS_2026-09-17.md`
- `docs/HP-04_IMPLEMENTATION_2026-09-24.md`
- `frontend/README.md`
- `frontend/scripts/smoke-state.mjs`
- `frontend/src/App.test.tsx`
- `frontend/src/README.md`
- `frontend/src/components/AppHeader.tsx`
- `frontend/src/features/capabilities/useCapabilities.ts`
- `frontend/src/features/settings/SettingsConflictDialog.tsx`
- `frontend/src/features/settings/settings-transactions.ts`
- `frontend/src/features/settings/useSettingsController.test.tsx`
- `frontend/src/features/settings/useSettingsController.ts`
- `scripts/bootstrap.py`
- `tests/fixtures/settings_bridge.py`
- `tests/test_backend_service.py`
- `tests/test_dependencies.py`
- `tests/test_desktop_bridge.py`
- `tests/test_installation_conflicts.py`
- `tests/test_settings_transactions.py`
