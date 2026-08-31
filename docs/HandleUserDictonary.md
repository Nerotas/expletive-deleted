# Task — Make User Profanity Dictionaries Durable and Independent of Repository Resources

## Context

The Profanity Censor application currently has bundled/default profanity resources in the repository.

The current implementation appears to use files under:

```text
resources/
```

as part of the live runtime dictionary.

The existing `policy.json` stores user changes as deltas against those resource files, meaning the application must continue rereading the repository/default resources to reconstruct the effective profanity policy.

That is not appropriate for the packaged desktop application.

When this application is distributed, users should not be expected to have or interact with the repository's `resources/` directory.

The bundled resource files should serve only as **starter/default templates**.

Once the application initializes a user's dictionary, the user's durable copy becomes the source of truth.

---

# 1. Required Architecture

Use this lifecycle:

```text
Bundled application resource
default profanity dictionary
        ↓
first run / first dictionary use
        ↓
seed durable user dictionary
        ↓
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\
        ↓
user dictionary becomes source of truth
```

After initialization, normal profanity detection must **not depend on rereading the bundled default files**.

---

# 2. Bundled Default Dictionary

Keep a default dictionary in the application resources.

Conceptually:

```text
resources/
├── profanity_censor_words.txt
└── profanity_exclusions.txt
```

or an equivalent packaged format.

These files exist to provide:

- Initial defaults
- Reset-to-default functionality
- Development/test fixtures

They are **not** the user's live dictionary.

Do not write user changes back into these packaged files.

---

# 3. User Dictionary Location

Store the user's durable profanity configuration beneath:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\
```

Recommended file:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json
```

This is application configuration/state rather than user media, so LocalAppData is appropriate.

User media continues to live under:

```text
Documents\Expletive Deleted\
```

Do not put the live dictionary inside the Electron installation directory.

Application upgrades/reinstalls should not normally replace the user's dictionary.

---

# 4. User Dictionary Should Be Complete

Do not continue storing only deltas from the bundled defaults.

The durable user dictionary should contain the **complete effective policy**.

Conceptual schema:

```json
{
  "schema_version": 1,
  "seeded_from_default_version": 1,
  "words": [
    "example"
  ],
  "exclusions": [
    "example exclusion"
  ]
}
```

Additional useful metadata may be included where justified, but do not over-engineer the format.

The important distinction is:

```text
OLD

bundled defaults
+
policy.json deltas
=
effective dictionary
```

becomes:

```text
NEW

user profanity.json
=
effective dictionary
```

---

# 5. First-Run Behavior

When the application needs the profanity dictionary:

```text
Does user profanity.json exist?
        │
        ├── YES
        │     ↓
        │   load it
        │
        └── NO
              ↓
        check for legacy configuration
              ↓
        migrate if necessary
              ↓
        otherwise seed from bundled defaults
              ↓
        write user profanity.json
              ↓
        load user dictionary
```

Initialization should be deterministic and safe.

---

# 6. Legacy `policy.json` Migration

Existing users must not lose their custom profanity choices.

The current behavior reportedly stores changes in `policy.json` as deltas while rereading the two bundled resource files.

Implement a one-time migration.

For an existing installation:

1. Read the bundled/default dictionary used by the legacy system.
2. Read the existing `policy.json`.
3. Apply all legacy additions/removals/exclusions exactly as the old application does.
4. Materialize the resulting **complete effective dictionary**.
5. Save it to:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json
```

6. Validate the new file.
7. Only after successful migration should the new dictionary become authoritative.

Do not discard legacy data before successful migration.

If appropriate, preserve the old file as a backup or leave it untouched once it is no longer used.

---

# 7. Runtime Source of Truth

After initialization/migration, all normal dictionary operations must use the user dictionary.

This includes:

```text
Profanity detection
Dictionary Settings UI
Add word
Remove word
Add exclusion
Remove exclusion
Search
Import
Export
```

The backend should not merge bundled defaults into every dictionary load.

---

# 8. Application Updates

Do **not** overwrite an existing user dictionary when the application is upgraded.

Example:

```text
Application v1
    ↓
user customizes dictionary
    ↓
Application v2 installed
    ↓
existing user profanity.json remains unchanged
```

A newer bundled default dictionary must not silently add or remove words from an existing user's policy.

The user controls their dictionary.

---

# 9. Default Dictionary Versioning

Version the bundled default dictionary sufficiently to identify which default set initially seeded the user's file.

For example:

```json
{
  "schema_version": 1,
  "seeded_from_default_version": 1
}
```

Do not confuse:

```text
schema_version
```

with:

```text
default dictionary version
```

They represent different things:

- `schema_version` = shape/format of the stored data
- default version = content revision of the application's starter dictionary

---

# 10. Restore Defaults

The Settings UI should eventually support:

```text
Restore Default Dictionary
```

This action should:

1. Require explicit user confirmation.
2. Replace the effective words/exclusions with the **current application's bundled defaults**.
3. Save the result into the user's durable dictionary.
4. Not cause the runtime to begin reading the bundled files directly again.

Conceptually:

```text
bundled defaults
      ↓
copy
      ↓
user profanity.json
```

---

# 11. Import / Export

Users should be able to move or back up their dictionary without manually navigating LocalAppData.

Provide or preserve:

```text
Import Dictionary
Export Dictionary
```

Export should produce a complete portable representation of the user's effective dictionary.

Import should:

- Parse the selected file
- Validate it
- Reject malformed input cleanly
- Avoid partially modifying the current dictionary on failure
- Save the successfully imported policy as the new user dictionary

Do not require users to manually edit files in AppData.

---

# 12. Atomic/Safe Writes

Dictionary writes should avoid corrupting the only copy if the process is interrupted.

Preferred conceptual approach:

```text
write temporary file
      ↓
validate
      ↓
replace existing profanity.json
```

Use the appropriate safe/atomic replacement mechanism for the backend/platform.

---

# 13. Backend Ownership

The Python backend remains the source of truth for:

```text
Dictionary paths
Parsing
Validation
Normalization
Persistence
Import
Export
Default seeding
Migration
```

The Electron frontend should not independently maintain another dictionary implementation.

Electron should request and update dictionary data through the backend/service boundary.

---

# 14. Suggested Backend Operations

Do not create API endpoints unnecessarily, but the service layer should conceptually support:

```text
Get effective dictionary
Add/update/remove words
Add/update/remove exclusions
Restore defaults
Import dictionary
Export dictionary
Report dictionary metadata
```

Example metadata:

```json
{
  "schema_version": 1,
  "default_version": 1,
  "word_count": 123,
  "exclusion_count": 12,
  "path": "C:\\Users\\...\\AppData\\Local\\ExpletiveDeleted\\dictionary\\profanity.json"
}
```

The exact API contract should follow the project's existing service design.

---

# 15. Failure Handling

Handle at minimum:

```text
LocalAppData unavailable
Dictionary directory cannot be created
Bundled defaults missing
Legacy migration failure
Malformed policy.json
Malformed user profanity.json
Write failure
Import validation failure
Permission error
```

Do not silently fall back to an unexpected policy when the user's existing dictionary is unreadable.

Report an actionable error.

---

# 16. Tests

Add tests covering:

```text
fresh install seeds user dictionary

fresh dictionary matches bundled defaults

second launch loads user dictionary without reseeding

adding a word persists

removing a word persists

adding an exclusion persists

removing an exclusion persists

application default changes do not silently modify existing user dictionary

restore defaults uses current bundled defaults

legacy policy.json migrates correctly

legacy additions survive migration

legacy removals survive migration

legacy exclusions survive migration

migration does not destroy source data on failure

malformed dictionary is handled safely

import valid dictionary

reject invalid import

export contains complete effective policy

safe write does not leave partial dictionary
```

---

# 17. Acceptance Criteria

This task is complete when:

1. `resources/` is used only to supply application defaults.
2. A fresh user receives a complete durable dictionary under LocalAppData.
3. The durable user dictionary becomes the runtime source of truth.
4. Normal dictionary loads no longer depend on repository resource files.
5. Existing `policy.json` users are migrated without losing customizations.
6. User changes survive application restart.
7. User changes survive normal application upgrades.
8. Bundled-default updates do not silently alter existing user policies.
9. Restore Defaults deliberately reseeds the user-owned dictionary.
10. Import/Export operate on complete dictionaries.
11. The Electron UI does not duplicate backend dictionary persistence logic.
12. Tests cover first-run initialization, persistence, migration, reset, and failure behavior.

---

# Guiding Rule

Treat:

```text
resources/
```

as:

> **the factory-default dictionary**

and:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json
```

as:

> **the user's dictionary**

Once the user dictionary exists, it is authoritative until the user explicitly changes, imports, or resets it.
