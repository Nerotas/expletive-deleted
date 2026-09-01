# Expletive Deleted Identity

> Obsolete planning record: the product rename is complete. This repository has not been
> released, so no earlier installed-user identity or state is supported or migrated.

Current identity:

- Display name: `Expletive Deleted`
- Application data: `%LOCALAPPDATA%\ExpletiveDeleted`
- Package slug and IPC prefix: `expletive-deleted`
- Windows AppUserModelID: `com.expletive-deleted.desktop`
- Renderer preload API: `window.expletiveDeleted`

Persisted settings use only `settings.ini`. Live dictionary state uses `censored.json`,
`exclusions.json`, and `discovered.json` beneath the application-data `dictionary`
directory. Combined dictionary JSON is supported only for explicit import and export.

The root Python entrypoints remain intentionally thin compatibility entrypoints as required
by `AGENTS.md`; that source-code compatibility policy is unrelated to product identity.
