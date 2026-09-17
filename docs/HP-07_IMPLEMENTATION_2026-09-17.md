# HP-07: Bound Windows media directories

`backend/filesystem/paths.py`, `windows.py`, and `operations.py` centralize path validation, root identity, directory leases, and identity-bound operations. `discovery.py` excludes staging and escaped links from library discovery. Inline comments explain non-obvious Windows sharing rules.

Configured roots may be junctions. Their resolved directory and device/file identity are captured once and stored in private `[root_bindings]` metadata in `settings.ini`, in the same atomic write as the selected paths. Renderer settings do not expose it. Unrelated edits retain it. A changed root fails validation; Settings remains reachable so the user can choose the intended target's actual folder path. Initialization moves no media.

Paths must be absolute and component-contained. Traversal, prefix lookalikes, device/network paths, alternate streams, reserved Windows names, trailing dots/spaces, source aliases, and escaped junctions are rejected. Ancestors are pinned before creating descendants. Both lexical junctions and resolved targets remain pinned during operations.

Directory handles deny deletion; junction handles also deny writes. Ordinary directories remain nonempty through a pinned child or a hidden, delete-on-close lease file while legitimate child renames remain permitted. Source read leases use the selected file as their guard, avoiding writes to read-only source folders. Deletion/rename uses the exact open file. See Microsoft's [CreateFile sharing contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) and [handle-based rename contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information).

Archive, restore, purge, submission, and settings replacement share the service lifecycle lock. Shared publication integration follows in [HP-06](HP-06_IMPLEMENTATION_2026-09-17.md).

## Tests, CI, and limits

Tests cover approved root/internal junctions, escapes, Unicode, invalid names, aliases, changed roots, persistence across restart, and new folder selection. Separate processes attempt parent rename and conversion into a junction. Conversion fails during the lease and succeeds after release, proving the native mutation is exercised.

Backend CI and private release/local Python validation explicitly run the filesystem gates. Windows junction tests require no symlink privilege and are not skipped on Windows.

Qualification covers Windows local storage. Network/device paths and protected mutations on non-Windows systems fail closed; POSIX descriptors alone do not prevent directory relocation. Native cross-volume/removable-drive behavior still needs hardware qualification. HP-05 source identity and legacy migration remain deferred.
