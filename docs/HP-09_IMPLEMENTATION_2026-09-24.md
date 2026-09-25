# HP-09: Preserve newer settings during onboarding

The walkthrough saves only its intended edits and progress. Component paths and unrelated preferences saved in the meantime survive. Same-field conflicts publish nothing and pause advancement until the user chooses **Keep current** or **Use my edit**. Cancel and failed saves retain the draft and current step.

## Implementation

- The wizard starts from the persisted snapshot, independently of the normal Settings form. Its baseline and draft remain separate from background query state. The baseline changes only after a confirmed save.
- `wizardChanges` allowlists the controls present in the wizard. Saved-step and Finish actions are explicit field comparisons, including when the requested value equals the baseline. This detects competing progress changes during Back/replay flows.
- Both directions use HP-04's existing backend transaction: thread/process locking, current persisted/effective settings, expected/current/proposed values, complete merged validation, atomic persistence and strict revision checking during resolution. Normal Settings still submits its complete draft and baseline; the backend derives intent. No second persistence or conflict mechanism was introduced.
- Wizard saves preserve unsaved normal Settings edits. Normal Settings continues to preserve edits made during a pending save and supports Discard to the latest persisted snapshot.
- A late folder-picker result updates the current wizard draft without overwriting other edits. If it arrives during a save, the confirmed baseline is retained but the wizard stays on the editable step. Duplicate saves and duplicate/incomplete resolution submissions are ignored.
- The shared dialog resets selections on a changed revision without remounting. It traps keyboard focus, supports radio keys and Escape, and restores the original save trigger. The controller captures that trigger before Save becomes disabled; the dialog defers restoration when the wizard has not yet re-enabled it.
- Back retains its existing non-saving behavior. Resume uses saved progress; replay starts at Welcome without resetting completion. Navigation after resolution follows the user's selected saved-step value. A readiness-refresh error after persistence is reported separately and does not turn a confirmed save into a failed wizard transaction.
- Short inline comments explain the draft ownership, allowlist, explicit progress, late picker, confirmed-save and focus-restoration rules. Queue polling remains independent of settings loading.

## Validation

Local Windows validation used repository Python 3.14.0 and Node.js 24.12.0:

- Shared backend transaction and installation-conflict suites: **31 passed**.
- Full backend discovery: **347 passed**, including invalid values, effective overrides, process contention, active work and persistence failures.
- Focused controller/dialog/wizard tests: **22 passed**, covering both choices, repeated conflicts, cancellation, failed saves, discard, double clicks, late responses, progress choices, Back, resume and replay/Finish.
- Full frontend suite: **205 passed** across 18 files. Typecheck, lint and production build passed; standard Electron smoke passed. The final wizard-only follow-up also passed all **nine** cases.
- Native state smoke: **nine required cases passed**. It changes real persisted backend settings between wizard steps, asserts no publication on conflicts, exercises keyboard choices/trapping/restoration and cancellation, forces a new conflict during resolution, reloads to resume saved progress, and checks final paths/preferences/progress. The same run checks setup/inspection races and confirms one installation worker and retained synthetic downloads.
- Conflict screenshots were inspected in light and dark modes at **1060x720** and **1440x940**. Native assertions also check horizontal content fit.
- Native setup recovery smoke: all **seven** cases passed, including **30,104 ms** of real silence, status-only retry, backend exit, worker saturation and explicit restart with retained files and fresh approval.

The initial native cancellation check exposed browser focus loss when Save became disabled; capturing the trigger and waiting for its re-enable fixed it. The final native state run passed without bypassing that assertion.

The offline native fixture substitutes component downloads and verification with local synthetic files while exercising real Electron, preload, Python service and persistence. No processing components were downloaded or installed. Packaged installer qualification and remote CI execution are outside this local validation.

## Required gates

Frontend CI explicitly requires the settings controller, shared dialog and wizard regression files, in addition to full coverage and existing typed/lint checks. Backend CI already explicitly requires shared settings transactions and component-conflict tests. The extended native state smoke remains mandatory in Electron CI, release validation, `scripts/run_all_tests.ps1` and local release builds. Release publishing behavior is unchanged.
