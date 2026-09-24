# Renderer developer guide

The renderer presents local backend state and collects user intent. Python owns validation, media safety, jobs, dependency setup, and persisted settings. Electron owns native dialogs and process lifecycle.

## Start here

| Change | Owner |
| --- | --- |
| Providers, query defaults, routing | `main.tsx`, `query-client.ts`, `App.tsx` |
| Navigation and global notifications | `components/AppHeader.tsx`, `components/ui/AlertBanner.tsx`, `App.tsx` |
| A backend operation or native action | `services/desktop-client.ts`; update `types/domain.ts` and the backend contract together |
| Queue polling and mutations | `features/queue/useQueue.ts`, `features/queue/queue-data.ts` |
| Combining jobs with library files, sorting, filtering, selection | `features/queue/queue-model.ts` |
| Queue layout and file actions | `features/queue/QueuePage.tsx`, `QueueView.tsx`, `QueueRow.tsx`, `ArchiveView.tsx` |
| Import, deletion, or YouTube dialogs | `features/queue/MediaDialogs.tsx`, `YoutubeDialogs.tsx` |
| Dictionary queries and mutations | `features/dictionary/useDictionary.ts` |
| Dictionary editor, table, or transcript review | `features/dictionary/DictionaryPage.tsx`, `DictionaryTable.tsx`, `ReviewDialog.tsx` |
| Settings drafts, saving, discarding, or path selection | `features/settings/useSettingsController.ts` |
| Settings fields | `features/settings/SettingsPage.tsx`, `MediaSettingsSections.tsx`, `RuntimeSettingsSection.tsx` |
| Setup plans, installation state, and progress | `features/capabilities/useCapabilities.ts`, `SetupProgressDialog.tsx` |
| Guided first-run steps | `features/onboarding/OnboardingPage.tsx` and the adjacent step/card components |
| Shared controls and browser behavior | `components/ui/`, `hooks/`, `utils/` |

Follow a queue action from `QueueRow` through `useQueue`, `desktopClient`, Electron preload, and the Python bridge. Results return through TanStack Query into the pure queue model and the view. Components do not interpret human-formatted CLI output.

Playback uses `desktopClient.openOutput(source)`; Python derives the output. Dictionary `importDictionary()` and `exportDictionary()` own their native picker flow and return cancellation as data. Do not introduce renderer-supplied launch/export paths or forward internal `native.*` methods through generic invoke.

Dictionary transaction ownership belongs to `backend/policy/transactions.py`; one-window lifecycle ownership belongs to `electron/single-instance.ts`. Renderer query serialization cannot replace these cross-process safeguards.

## State ownership

- **Backend state:** TanStack Query caches capabilities, settings, dictionary pages, and queue snapshots. Feature controllers coordinate mutations and refresh their affected queries.
- **Editable settings:** React Hook Form retains a separate draft. Background settings refreshes may reset a clean form, but must not replace a dirty draft. Save submits the complete draft; Discard restores the persisted snapshot.
- **View state:** selection, filters, sort order, widths, and dialogs stay local to their page/view. Queue selection is intersected with current eligibility before submission. Running jobs remain visible above filters.
- **Session bookkeeping:** first-seen copy-job dates belong to the queue controller instance, not module globals. They are temporary display values, not backend timestamps.
- **Onboarding:** the wizard owns a temporary settings snapshot and persists progress explicitly. See the review report for the outstanding stale-snapshot issue after component setup.

The app shell keeps controllers mounted across navigation so settings drafts and setup progress survive route changes. Queue polling is enabled for Queue and Onboarding; it must not reload settings. Dictionary censored-word queries require the user's reveal choice.

## Adding a feature

1. Put feature-specific components, hooks, pure helpers, and tests in that feature folder. Keep a page focused on composition and interactions. Extract by responsibility, not a fixed line limit.
2. Add typed desktop operations in `services/desktop-client.ts`. Keep wire method strings there. Do not import Node/Electron or call the preload bridge in feature code; ESLint enforces these common boundary violations. This is a development guard, not an IPC security boundary.
3. Put backend mutations and error handling in a controller. Handle every rejected native-dialog or external-link promise; `void` alone does not handle rejection.
4. Add concise comments explaining non-obvious ordering, cleanup, privacy, or state rules. Avoid comments that merely repeat a component name or assignment.
5. Keep feature styles in the adjacent CSS file. These styles are global today, so scope selectors with feature classes. Shared tokens live in `theme.css`; shared layout and controls live in `App.css` and `index.css`.
6. Test safety-relevant behavior in pure helpers or hooks, then use app integration tests for routing, settings drafts, and workflow interactions. Reuse `test/fixtures.ts` and an isolated query client.

## Validation

Run from `frontend/`:

```powershell
npm test -- run src/features/queue/queue-model.test.ts src/hooks/use-column-resize.test.tsx
npm test
npm run typecheck
npm run lint
npm run smoke
```

`smoke` includes the production build and launches native Electron with isolated application data. It checks onboarding, preload, routing, and dictionary behavior and writes screenshots into ignored `test-results/`. Inspect light/dark screens for meaningful visual changes. Use `npm run smoke:shutdown` when changing Electron lifecycle or backend shutdown. Installer validation is documented in [the frontend README](../README.md).

See [the frontend inspection report](../../docs/FRONTEND_REVIEW_2026-09-16.md) for validation results and remaining risks. Passing type checks does not validate arbitrary IPC payloads at runtime.
