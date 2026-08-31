# Task — Complete Application Rename from `Profanity Censor` to `Expletive Deleted`

## Context

The project was originally named:

```text
Profanity Censor
```

The current application name is:

```text
Expletive Deleted
```

The repository has already moved toward the new name:

```text
expletive-deleted
```

but the rename has **not been completed throughout the application**.

There are still runtime paths, configuration locations, labels, constants, tests, and potentially packaging metadata using the old `Profanity Censor` name.

For example, current user data may still be stored under paths such as:

```text
%LOCALAPPDATA%\Profanity Censor\
```

The new application-managed location must be:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

This task must be completed **before implementing the new durable user-dictionary architecture**, because the dictionary work will create long-lived user data beneath the application-data root.

We do not want to deliberately create new durable files under the obsolete application name.

---

# 1. Naming Convention

Use these names consistently according to context.

## Product / Display Name

Use:

```text
Expletive Deleted
```

This is the human-facing application name.

Use it for things such as:

- Window titles
- Headings
- Setup screens
- About information
- Installer display name
- User-facing messages
- Documentation describing the application

---

## Application Data Namespace

Use:

```text
ExpletiveDeleted
```

for application-managed Windows filesystem data.

Target root:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

Do not use:

```text
%LOCALAPPDATA%\Profanity Censor\
```

and do not introduce:

```text
%LOCALAPPDATA%\Expletive Deleted\
```

unless an existing platform API imposes that location.

The intended canonical application-data root is:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

---

## User Documents

User-facing media should retain the readable product name with spaces:

```text
%USERPROFILE%\Documents\Expletive Deleted\
```

For example:

```text
%USERPROFILE%\Documents\Expletive Deleted\
├── Ready\
├── Finished\
├── Processed\
└── Transcripts\
```

These are user-owned files and should use the human-readable application name.

---

## Repository / Package-Style Identifier

Where a lowercase slug is appropriate, use:

```text
expletive-deleted
```

Do not mechanically replace identifiers without first checking what each field is used for.

For example, package names, executable identifiers, application IDs, and Electron packaging metadata may have different formatting requirements.

---

# 2. Audit the Entire Repository First

Before changing code, search the repository for all old-name variants.

At minimum search for:

```text
Profanity Censor
ProfanityCensor
profanity-censor
profanity_censor
PROFANITY_CENSOR
```

Also inspect case variations where relevant.

Do not blindly replace every occurrence.

The existing Python class:

```text
ProfanityCensor
```

may represent the censorship engine rather than the product name.

If that class is an established processing abstraction, **do not rename it merely for cosmetic consistency** unless there is a concrete architectural reason.

The purpose of this task is to rename the **application/product identity and its persistent paths**, not to unnecessarily rename stable internal censorship concepts.

---

# 3. Centralize Application Identity

Avoid scattering literal application names and filesystem directory names throughout the codebase.

Establish one appropriate source of truth for application identity/path naming.

Conceptually:

```text
Display Name: Expletive Deleted
App Data Directory Name: ExpletiveDeleted
Documents Directory Name: Expletive Deleted
```

Use the project's existing configuration/path architecture if one already exists.

Do not add a second competing configuration system.

The backend and Electron frontend should not independently invent different filesystem roots.

---

# 4. Update Local Application Data Paths

All application-managed persistent data should resolve beneath:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

This includes current or planned resources such as:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
├── dictionary\
├── dependencies\
├── models\
├── cache\
├── logs\
└── settings\
```

Only create directories that the application actually needs.

This is the namespace that future work should use for:

- User profanity dictionary
- FFmpeg installed/retrieved for application use
- Whisper model storage/cache where explicitly managed
- Settings
- Logs
- Other application-owned runtime state

---

# 5. Preserve User-Facing Media Paths

Ensure default user media paths use:

```text
%USERPROFILE%\Documents\Expletive Deleted\
```

and not:

```text
%USERPROFILE%\Documents\Profanity Censor\
```

Target defaults:

```text
Documents\Expletive Deleted\Ready
Documents\Expletive Deleted\Finished
Documents\Expletive Deleted\Processed
Documents\Expletive Deleted\Transcripts
```

Do not overwrite user-customized directory settings just because the application name changed.

If a user has explicitly configured another directory, preserve that choice.

---

# 6. Existing User Data Migration

This rename must not strand existing local application state.

Detect the legacy application-data root:

```text
%LOCALAPPDATA%\Profanity Censor\
```

and the new root:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

For an existing user, migration should be safe and deterministic.

Conceptually:

```text
new app-data root exists?
        │
        ├── YES
        │     ↓
        │   use new location
        │
        └── NO
              ↓
        legacy root exists?
              │
              ├── YES
              │     ↓
              │   migrate applicable data
              │     ↓
              │   validate
              │     ↓
              │   use new root
              │
              └── NO
                    ↓
              initialize new root normally
```

Do not delete legacy data before successful migration.

---

# 7. Migration Scope

First inspect what currently exists under the legacy application-data location.

Potential contents may include:

```text
settings
policy.json
dictionary-related state
dependency paths
model paths/cache references
logs
other runtime configuration
```

Migrate actual durable state that belongs to the user/application.

Do not blindly copy:

- Temporary files
- Invalid caches
- Obsolete build artifacts
- Files that should be regenerated

Determine migration behavior from the existing implementation.

---

# 8. Important Dictionary Interaction

The following dictionary task will run **after this rename task**.

That task will introduce the canonical durable dictionary:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json
```

Therefore this rename task must ensure that any existing legacy dictionary/policy information currently stored under:

```text
%LOCALAPPDATA%\Profanity Censor\
```

remains discoverable for the subsequent dictionary migration.

In particular:

> Do not delete or lose the existing legacy `policy.json` or other user dictionary choices.

The upcoming dictionary task must still be able to migrate those choices into the new complete user dictionary.

If this rename task moves `policy.json`, preserve enough information for the dictionary migration code to recognize that it is legacy policy data.

---

# 9. Electron Application Identity

Inspect Electron configuration and update obsolete product-name references where appropriate.

Check at minimum:

- `package.json`
- Electron main process
- Window titles
- Application menu labels
- Dialog titles
- About metadata
- Packaging configuration
- Installer configuration
- Executable/product display names
- Shortcut names
- Application user-model identifiers if currently defined

Use:

```text
Expletive Deleted
```

for human-facing product names.

Do not casually change stable machine identifiers if doing so would create an unnecessary migration problem.

If an existing machine identifier needs to remain for compatibility, document that decision.

---

# 10. Frontend Copy

Search the Electron renderer for old user-facing strings.

Replace obsolete product references such as:

```text
Profanity Censor
```

with:

```text
Expletive Deleted
```

where the text is referring to the application itself.

Do not replace legitimate generic phrases such as:

```text
profanity censor method
profanity censor dictionary
```

when they describe functionality rather than the product name.

---

# 11. Backend Paths

Trace all backend path construction.

There should not be independent hardcoded variants such as:

```python
"Profanity Censor"
"Expletive Deleted"
"ExpletiveDeleted"
```

scattered throughout modules.

Path construction should use the centralized application path configuration.

Verify areas including:

- Settings persistence
- Policy storage
- Dependency paths
- FFmpeg management
- Whisper/model management
- Logs
- Cache
- Future dictionary storage

---

# 12. Resource Folder Is Not Renamed for Runtime Identity

Repository resources such as:

```text
resources/
```

may remain named according to their technical purpose.

Do not rename files or modules simply because they contain the word `profanity` when that word correctly describes their function.

Examples that may legitimately remain:

```text
profanity_censor_words.txt
profanity_exclusions.txt
ProfanityCensor
detect_profanity()
```

This task is an **application identity migration**, not a terminology purge.

---

# 13. Documentation

Update active project documentation where it describes the current application as `Profanity Censor`.

Use:

```text
Expletive Deleted
```

for the product.

Historical documentation may retain the old name where it is explicitly describing the former project/baseline.

Do not rewrite historical context in a misleading way.

---

# 14. Tests

Add/update tests for path and migration behavior.

At minimum cover:

```text
fresh install resolves LocalAppData to ExpletiveDeleted

fresh install resolves Documents root to Expletive Deleted

legacy Profanity Censor app-data location is detected

legacy durable settings survive migration

legacy policy/dictionary state remains available

new location wins when valid new state already exists

migration does not delete legacy data on failure

custom user media directories are not reset during rename

product-facing application name is Expletive Deleted
```

If path logic already has tests, extend those instead of creating duplicate testing infrastructure.

---

# 15. Do Not Do

Do not:

```text
blind global search-and-replace every use of "profanity"

rename the ProfanityCensor engine solely for branding

delete legacy AppData before validating migration

reset users' customized media directories

create new durable files under the old Profanity Censor path

introduce multiple competing path constants

rename repository resources unnecessarily

perform unrelated architectural refactors
```

---

# 16. Acceptance Criteria

This task is complete when:

1. The user-facing product name is **Expletive Deleted**.
2. New application-managed data resolves beneath:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

3. Default user media resolves beneath:

```text
%USERPROFILE%\Documents\Expletive Deleted\
```

4. No new persistent application state is deliberately created beneath:

```text
%LOCALAPPDATA%\Profanity Censor\
```

5. Existing durable state from the legacy location can be migrated safely.
6. Existing dictionary/policy choices remain available for the following dictionary-migration task.
7. Explicit user-selected media directories are preserved.
8. Electron and Python resolve paths consistently.
9. Relevant product-facing `Profanity Censor` references have been replaced.
10. Functional/internal profanity terminology has not been renamed unnecessarily.
11. Tests cover fresh paths and legacy migration.
12. The repository is ready for the subsequent **durable user dictionary** task.

---

# Sequencing

Complete this task first.

Then proceed with:

> **Make User Profanity Dictionaries Durable and Independent of Repository Resources**

That subsequent task should assume the canonical application-data root is already:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
```

and should create the user dictionary at:

```text
%LOCALAPPDATA%\ExpletiveDeleted\dictionary\profanity.json
```