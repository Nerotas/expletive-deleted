# User-Fetched Python Runtime Plan

Status: proposed migration for Windows x64. This document describes the
replacement for the currently implemented Python-in-installer contract. It does
not change the release contents by itself.

## Decision and outcome

The Windows installer should contain the Electron application and first-party
Python backend source, but no Python interpreter, pip payload, processing
package, external media tool, or speech model. On first launch, a parent can:

1. Review and approve retrieval of the pinned application-managed Python
   runtime; or
2. Explicitly select an existing compatible Python installation and approve
   the separate processing-package setup.

The managed path is the recommended experience. It remains local to the
current Windows user, does not require elevation, and does not modify the
system `PATH`, registry, or another Python installation. No download starts
before the user approves the exact plan.

## Recommended Python artifact

Retrieve the pinned official CPython x64 NuGet package directly from NuGet's
v3 package endpoint. CPython publishes this package as part of its Windows
release process; it is a passive ZIP-compatible archive and includes pip. The
current implementation pin is Python 3.13.15, so the first bootstrap manifest
should review and pin the `python` 3.13.15 package rather than selecting a
floating version.

Do not use the Windows embeddable package for this flow. It intentionally omits
pip and applies an isolated `._pth` configuration, which would require a second
bootstrap artifact and custom path mutation before the existing approved
package installer could run. Do not silently run the traditional Python
installer or install the Python Install Manager; both change the machine beyond
the application's private runtime directory.

Primary references:

- [CPython NuGet package](https://www.nuget.org/packages/python/3.13.15)
- [Python 3.13.15 release artifacts](https://www.python.org/downloads/release/python-31315/)
- [Python 3.13 Windows embeddable-package guidance](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)
- [PEP 773 Windows distribution details](https://peps.python.org/pep-0773/)

Before implementation, add a reviewed bootstrap record containing the exact
package ID, version, immutable URL, expected download size, registry-provided
SHA-512 value, independently recorded SHA-256 value, Python and pip versions,
license identifiers, and required license paths. A version update is a reviewed
source change, not a runtime lookup for “latest.”

## Bootstrap architecture

Python currently owns dependency planning and installation, so it cannot
install itself. The Python bootstrap must be a narrow Electron main-process
service that is available before the backend bridge starts.

```text
Electron launch
  -> inspect managed or explicitly selected Python
  -> show Python setup page when no verified runtime exists
  -> disclose source, version, license, size, destination, and network use
  -> download to a temporary application-data directory after approval
  -> verify hashes, archive paths, payload, version, architecture, pip, and license
  -> atomically publish the versioned runtime
  -> start the Python bridge without restarting Electron
  -> continue through the existing processing-component onboarding
```

Implement the bootstrap as a restartable state machine rather than another
branch in the current backend error page:

- `missing`: no verified managed or explicitly selected interpreter exists.
- `planning`: an immutable Python retrieval plan is ready for review.
- `downloading`: bytes are written only to a unique partial directory.
- `verifying`: the archive and relocated interpreter are being checked.
- `ready`: a versioned runtime manifest points to a verified `python.exe`.
- `failed` or `cancelled`: no partial runtime is published, and retry is safe.

The renderer receives only typed bootstrap status and commands through preload.
It must not receive arbitrary filesystem, process, URL, or shell access. Suggested
preload operations are `getPythonStatus`, `planPythonInstall`,
`installPython`, `cancelPythonInstall`, and `selectExistingPython`. Once Python
is ready, Electron starts the existing private JSON-line bridge and the current
typed desktop client takes over.

## Filesystem contract

Keep the runtime separate from the already implemented writable package target:

```text
%LOCALAPPDATA%\ExpletiveDeleted\
  dependencies\
    python-runtime\
      3.13.15\
        tools\python.exe
        ...
      runtime-manifest.json
    python\
      ... user-approved processing packages ...
  downloads\
    partial\
```

`dependencies\python` remains the `CENSOR_PYTHON_PACKAGES_DIR`, which lets an
upgrade reuse already verified packages when their versions and CPython ABI are
compatible. Runtime publication writes a manifest to a temporary sibling,
flushes and verifies it, then renames the completed version into place. Keep the
previous verified runtime until the new bridge starts successfully so an update
can roll back without touching media or settings.

Never extract directly over an existing runtime. Reject absolute archive paths,
`..` traversal, alternate data streams, symlinks, junctions, reparse points,
duplicate case-insensitive paths, unexpected executables, destination
collisions, and payloads above reviewed file-count or expanded-size limits.

## Verification and trust policy

The Electron bootstrap must:

- Allow only the exact reviewed HTTPS host and artifact URL, with redirects
  constrained to an explicit allowlist.
- Verify the registry-provided SHA-512 and the repository-pinned SHA-256 before
  extraction.
- Generate a local file manifest after extraction and retain Python and pip
  license notices with the runtime.
- Launch the relocated interpreter with isolation flags to verify exact CPython
  version, 64-bit architecture, `sys.prefix`, SSL support, and the approved pip
  version.
- Reject prerelease, free-threaded, 32-bit, Store-alias, or otherwise
  incompatible interpreters.
- Load packages only from the application-managed package directory; never use
  ambient user-site packages.
- Fail closed if a previously managed runtime is missing, modified, or cannot
  start. Do not fall back silently to `py`, `python`, or a configured system
  interpreter.

An existing Python is usable only after the user selects it and the same
version, architecture, relocation-independent startup, and package-isolation
checks pass. Record that explicit selection in application settings and provide
a visible way to return to the managed runtime.

## User experience

The application window must open even when Python is absent. Replace the current
repair dead end with a pre-backend setup page written in plain language:

- Explain that Python runs the local transcription service and that no media is
  uploaded.
- Show the exact version, source, license, download size, estimated extracted
  size, application-data destination, and that network access is required.
- Offer **Review Python download** as the primary action and **Use Python already
  installed** as the secondary action.
- Keep approval and installation separate. Closing the disclosure starts
  nothing.
- Show determinate byte progress when available, cancellation, actionable
  checksum/network/disk errors, and a retry that preserves a valid prior
  runtime.
- Start the backend automatically after verification and continue onboarding
  with transcription packages, FFmpeg/FFprobe, YouTube tools, and the Whisper
  model still listed as separate approvals.

Do not describe Python as installed with the application after this migration.
Update onboarding, setup bands, settings, repair guidance, README files, and
uninstall language together.

## Implementation phases

### 1. Approve and pin the bootstrap input

- Update the product decision in `AGENTS.md` and
  `docs/BUNDLED_RUNTIME_PACKAGING_PLAN.md` before changing release contents.
- Add a schema-validated Python download manifest under
  `frontend/runtime/windows-x64/` with the reviewed NuGet artifact metadata.
- Complete the Python/pip licensing and source review and record how notices are
  retained after the user fetch.
- Measure download and extracted sizes rather than hard-coding estimates from a
  web page.

### 2. Add the Electron-owned bootstrap

- Add focused modules under `frontend/electron/` for status inspection, immutable
  planning, download progress, cancellation, safe extraction, verification,
  atomic publication, and rollback.
- Refactor `startBridge` in `frontend/electron/main.ts` so it can start after a
  successful bootstrap and cleanly restart after runtime repair.
- Replace `requireBundledRuntime` with managed-runtime discovery. Preserve the
  packaged fail-closed behavior and the source-checkout `.venv` workflow.
- Add narrow bootstrap IPC handlers and preload methods with runtime validation
  of every payload.

### 3. Add the pre-backend setup UI

- Gate normal renderer data hooks until the Python bootstrap reports `ready`.
- Add the Python disclosure, progress, locate-existing, failure, cancel, and
  retry states without depending on `settings.get` or another backend call.
- After the bridge starts, refresh settings and capabilities and enter the
  existing onboarding flow in the same application session.

### 4. Align Python package installation

- Continue installing pinned processing packages into
  `%LOCALAPPDATA%\ExpletiveDeleted\dependencies\python` with `--target`.
- Include the runtime identity and CPython ABI in dependency verification so an
  incompatible runtime change cannot reuse compiled packages accidentally.
- Invalidate import caches after approved installation and verify readiness
  before reporting processing as available.

### 5. Remove Python from release packaging

- Remove `app-runtime/python` from `frontend/electron-builder.yml` and delete the
  bundled-runtime staging requirement from package scripts.
- Remove the release steps that copy, assemble, and inject private Python. Keep
  `actions/setup-python` only where CI needs it to run backend tests.
- Change the package audit to fail if any Python executable, pip payload, Python
  DLL, `.pyd`, wheel, or legacy runtime manifest appears in installed resources.
- Rename the setup-first package and smoke commands so their names describe a
  Python-free installer rather than a bundled runtime.
- Update the installer SBOM and notices to list only artifacts actually shipped;
  retain Python/pip notices with the fetched runtime instead.

### 6. Migrate documentation and diagnostics

- Update `README.md`, `QUICKSTART.md`, `TROUBLESHOOTING.md`, `PROJECT_SUMMARY.md`,
  `frontend/README.md`, and system-check documentation in the same change.
- Distinguish download failures, integrity failures, unsupported existing
  Python, runtime startup failures, and backend protocol failures.
- State clearly that uninstalling the application leaves user-fetched tools and
  models in application data unless a separate, explicit removal feature is
  approved.

## Test and release plan

Unit and integration coverage must include:

- Stable plan IDs that change when source, version, hash, destination, or license
  changes.
- No network call before consent and no install when a plan is stale.
- Hash mismatch, truncated download, unexpected redirect, unsafe archive path,
  duplicate path, insufficient disk space, cancellation, and interrupted
  publication.
- Exact Python version, x64 architecture, pip, SSL, package isolation, manifest,
  and tamper verification.
- Explicit existing-Python selection and rejection of ambient or incompatible
  interpreters.
- Bridge startup in the same Electron session after install, plus retry and
  rollback after a failed runtime update.
- Renderer accessibility and keyboard behavior for every bootstrap state.

CI must not depend on a live Python or NuGet download for ordinary pull-request
tests. Serve a pinned test archive from a local fixture for download/extraction
tests. For packaged smoke, build the installer without Python, launch it with a
clean `PATH` and empty application data, and verify that the Python disclosure
appears without a repair error. Then seed a separately prepared, verified Python
runtime under the temporary application-data root and prove that Electron starts
the backend and reaches normal onboarding. The release workflow should perform
one network-backed clean-machine qualification against the reviewed artifact
before publication.

## Acceptance criteria

The migration is complete only when:

1. Package audit proves the installer and installed resources contain no Python
   runtime or pip payload.
2. A clean offline launch opens an actionable Python setup page without starting
   a download or requiring a terminal.
3. Approval discloses the exact Python source, version, licenses, sizes,
   destination, and network use.
4. A tampered or unexpected artifact cannot be extracted or launched.
5. Cancellation and failure publish no partial runtime and preserve any prior
   verified runtime.
6. A successful fetch starts the backend in the same app session and continues
   the existing setup flow.
7. Python packages, tools, models, settings, and media remain outside installed
   application resources and source media is never touched by setup.
8. Full backend, frontend, Electron, package-audit, clean-machine bootstrap, and
   packaged smoke validation pass on Windows x64.

## Main risks and mitigations

- **Bootstrap complexity moves into Electron.** Keep the service narrow, typed,
  state-driven, and independently tested; do not duplicate general backend
  dependency management in JavaScript.
- **Artifact layout may change.** Pin the exact package and validate a strict
  payload contract before atomic publication.
- **Existing Python installations vary.** Make selection explicit and enforce a
  narrow supported ABI instead of accepting any executable named `python.exe`.
- **Updates can strand compiled packages.** Version runtime directories and key
  package verification to the CPython ABI before reuse.
- **Corporate proxies or security products may interrupt retrieval.** Preserve
  resumable user-facing failure details and provide the explicit existing-Python
  path; do not weaken TLS or hash verification.

## Out of scope

- Bundling any Python runtime or processing dependency as a fallback.
- Automatically installing Python system-wide or changing Windows `PATH`.
- Supporting a floating “latest Python” channel.
- Changing the supported Whisper model, media-safety contract, or local-only
  processing policy.
- Adding macOS or Linux packaging before the Windows bootstrap is qualified.
