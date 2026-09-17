# Frontend structure and maintainability review

Date: 2026-09-16

## Assessment

The renderer has a sound foundation: feature folders, typed desktop operations, React Router, TanStack Query for backend state, and React Hook Form for settings drafts. The main maintenance problem was responsibility concentration inside page files. This pass separates those responsibilities while preserving the existing rendered controls, copy, CSS, and backend protocol.

The scope covered renderer routes, feature controllers, queue calculations, settings lifecycle, dictionary workflows, onboarding composition, setup state, shared controls, styling ownership, desktop-client usage, lint/build configuration, and existing test coverage. Electron main/preload were checked as the integration boundary; their outstanding security and transport issues require a separate bridge change. This review does not certify that every runtime error is resolved.

## Completed changes

| Area | Previous concern | Result |
| --- | --- | --- |
| Queue | One 785-line page combined job/library projection, sorting, table rendering, row actions, archive, and dialogs | A 204-line page composes focused views and dialogs; `queue-model.ts` owns pure calculations; `queue-data.ts` owns snapshot loading |
| Queue polling | Status sets were duplicated and copy timestamps lived in a module-global map | One set of status definitions; first-seen dates scoped to the controller |
| Resize lifecycle | Pointer listeners were removed on release/cancel/blur, but not on table unmount | `use-column-resize.ts` removes all listeners on unmount and before a replacement drag |
| App shell | Installation progress rendering, timing, and formatting inflated `App.tsx` to 322 lines | Progress belongs to the capability feature; shell is 186 lines |
| Settings | A 314-line page mixed every settings section | A 114-line page composes media and runtime sections; saving/draft behavior remains in the controller |
| Dictionary | Table sorting, pagination, and rendering lived inside the editor page | `DictionaryTable.tsx` owns table presentation; editor and query controller retain their existing responsibilities |
| Architecture enforcement | Typed-client usage was a convention only | Renderer lint rules reject Node/Electron imports and direct preload member access outside the typed client |
| Onboarding developers | File placement and state ownership required following implementation details | Added `frontend/src/README.md` with ownership map, action flow, state rules, extension guidance, and validation commands |

Inline comments explain pending-job precedence, selection changes during polling, drag event nesting, first-seen copy timestamps, settings draft preservation, sensitive-word fetching, indeterminate setup progress, and listener cleanup. No packages were added.

## What remains solid

- Renderer features use structured desktop-client operations; raw backend method names stay at that boundary.
- App-level controllers preserve drafts and setup state across navigation.
- Queue polling does not reload settings.
- Onboarding already uses focused step and card components; no further mechanical split was needed.
- Backend validation and verified-artifact gates remain authoritative. UI eligibility checks do not replace those safeguards.
- Existing app integration tests cover save/discard, setup consent, dictionary visibility, queue actions, and onboarding. New focused tests exercise calculations and cleanup without booting the whole app.

## Remaining findings and recommended follow-up

These findings were observed in source inspection and remain open; the structural changes above do not fix them.

| Priority | Finding and evidence | Follow-up |
| --- | --- | --- |
| High | `features/capabilities/useCapabilities.ts` polls setup with `setInterval`, permits overlapping requests, and suppresses status/cancel failures. A slow or failed bridge can leave stale progress; responses can arrive out of order. | Use a serialized polling lifecycle with stale-response protection and surfaced recoverable failures. Coordinate request deadlines with the bridge. |
| High | `features/onboarding/OnboardingPage.tsx` captures a full settings snapshot at mount and saves it on each step. Component setup can update persisted runtime paths while this snapshot stays stale. | Reconcile backend-managed fields or use a revision-aware update contract before saving wizard changes. |
| Medium | `features/dictionary/useDictionary.ts` converts an update failure into a resolved promise; `DictionaryPage.tsx` then clears the entered word. Import/export pickers sit outside the mutation error handlers. | Return explicit mutation outcomes, retain rejected edits, and include picker failures in the controller error path. |
| Medium | `features/queue/queue-data.ts` fetches all events for every retained job on every poll. Pure row projection also repeatedly scans job history for each file. | Add backend event cursors/latest-event summaries and measure large queues before optimizing selectors or introducing virtualization. |
| Medium | Modal components have dialog semantics, but no shared focus trap, focus restoration, or consistent Escape handling. Direct external-link handlers also do not consistently report rejected promises. | Introduce one tested accessible dialog primitive and a shared native-action error path. Preserve explicit destructive-action consent. |
| Medium | `features/onboarding/BackendSetupPage.tsx` implements Try again with renderer reload; `electron/main.ts` starts the Python child only at app readiness. | Make recovery invoke a bounded main-process restart operation or use accurate restart guidance. |
| Existing bridge risk | Electron still lacks comprehensive sender/navigation validation; generic IPC remains typed by assertion rather than fully runtime validated. File-opening and transport limitations from the earlier bridge review remain. | Address these in the bridge itself. Renderer lint guards are not security enforcement. |
| Maintenance | `App.test.tsx` remains a large integration suite; CSS is globally scoped and some feature components use dense JSX. | Keep new unit tests beside their owners. Extract integration fixtures and dialog primitives when changing those areas; avoid broad formatting-only rewrites. |

## Validation

- Focused regression tests: 12 passed, covering pending/historical job precedence, pre-discovery copies, YouTube retry visibility, selection and queue ordering, resize clamping, drag termination, replacement drag, and navigation cleanup.
- Full frontend suite: 86 tests passed across 8 files.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- ESLint boundary probes: rejected Electron imports and direct preload access; accepted typed-client usage.
- Production build and native Electron smoke: passed, including backend startup, preload, onboarding, routing, dictionary reveal/cancel, and dark navigation contrast.
- Inspected native screenshots of Settings in light/dark mode and the dictionary confirmation at the minimum window width. Queue viewport screenshots were also captured at 1440×940 and 1060×720; screenshots remain in ignored `frontend/test-results/`.

No new Windows installer was produced in this pass. Installer/runtime packaging, actual model downloads, live YouTube sessions, and full media processing were not revalidated. Earlier backend and bridge reports remain separate from this frontend change.

## Simple postmortem

The folder structure was already sensible, but page files had accumulated unrelated responsibilities and one drag handler lacked teardown on navigation. The changes make ownership explicit, move calculations into testable modules, and enforce the intended renderer boundary. Future work should follow the developer guide and address the open setup/error-recovery findings before treating the frontend as fully hardened.
