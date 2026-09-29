# Bundle the Windows processing runtime with FFmpeg/x264, matching sources, and third-party licenses

## Goal

Ship a Windows x64 installer containing the processing tools and Python packages needed by Expletive Deleted, including a working `libx264` encoder. Users should not need to install Python, FFmpeg, or yt-dlp themselves. Keep the application's own code MIT-licensed and preserve each dependency's applicable license.

This issue proposes replacing the current Python-only installer policy. It is an implementation specification, not a claim that the existing installer already complies with the requirements of a future bundle. Approving implementation of this issue should explicitly approve the revised distribution policy.

## Reviewed baseline

Repository: https://github.com/Nerotas/expletive-deleted

Reviewed commit: `b31cc3ad6d080a760cc8a052cc0305dff6f66113` (September 27, 2026). Reconcile these findings with subsequent changes before implementation.

| Area | Observed behavior | Required change |
| --- | --- | --- |
| `AGENTS.md`, `docs/BUNDLED_RUNTIME_PACKAGING_PLAN.md` | Explicitly prohibit bundling processing dependencies | Adopt the new bundle policy and update the associated audits |
| `frontend/scripts/build-audited-runtime.ps1` | Generates Python/pip runtime notices and inventory | Inventory and preserve notices for the complete shipped runtime |
| `frontend/scripts/audit-bundled-runtime.mjs`, `audit-package.mjs` | Reject processing tools/packages, including encoder libraries | Permit reviewed, pinned components; reject unapproved components |
| `scripts/download_ffmpeg_runtime.py` | Obtains executables through `static-ffmpeg`, copies them, and records paths | Replace release-time acquisition with exact binary/source provenance |
| `backend/runtime/dependency_specs.py` | FFmpeg identified as “8.0 or later” | Record an exact bundled build identity; distinguish this from minimum compatibility requirements for external tools |
| `backend/runtime/dependency_plan.py` | Labels downloaded `yt-dlp.exe` as Unlicense | Use the license of the actual executable, including GPL-covered dependencies |
| `.github/workflows/release.yml` | Publishes the installer | Publish the source companion, notices, inventory, and checksums as well |
| `backend/runtime/encoders.py` | Prefers platform encoders and falls back to `libx264` | Retain x264 availability and verify its packaged operation |

The existing installer intentionally excludes these processing tools. Missing bundle materials are preparation gaps for this proposed change, not proof of an existing unlawful distribution. A finished installer and the exact upstream binaries have not been audited in this review.

## Proposed distribution decisions

| Component | Proposed treatment |
| --- | --- |
| Private CPython and pip | Retain the private runtime and its licenses; never depend on system Python |
| FFmpeg and FFprobe | Bundle an exact redistributable GPL build with `libx264`, matching sources, and build materials |
| faster-whisper and its Python dependencies | Bundle a reviewed, hash-locked Windows wheel set and all required notices/source materials |
| yt-dlp | Bundle the pinned official Windows executable; treat it according to its bundled-executable license, not the repository's Unlicense alone |
| Deno | Bundle the reviewed runtime required by the chosen yt-dlp version, with its notices |
| Whisper model | Keep the large model as an explicit first-run download; record its revision, license, and verification information |
| CUDA/cuDNN and other optional GPU runtimes | Do not add by default; any included GPU redistribution requires a separate inventory and review |
| Electron/Chromium | Preserve existing upstream license/notice artifacts, including Chromium's own `ffmpeg.dll`; this DLL is not the processing executable |

The model-download boundary and GPU exclusion are proposed scope decisions, not GPL requirements. Preserve the current `preserve_source` video default; keep H.264 conversion available. Changing encoder preference or the default video mode is outside this issue.

## Implementation checklist

### 1. Establish exact binary and source provenance

- [ ] Introduce a versioned bundle lock/manifest identifying each component, version/commit, platform, architecture, upstream download location, binary SHA-256, applicable license, notice locations, and matching source/build-material locations and hashes.
- [ ] Prefer a documented upstream FFmpeg build whose exact source, patches, dependencies, and build recipe are obtainable. If those cannot be obtained, build FFmpeg/x264 from pinned sources in CI. Do not invent missing upstream provenance.
- [ ] Capture `ffmpeg -version`, `ffmpeg -buildconf`, `ffmpeg -L`, and FFprobe's version for the selected binaries.
- [ ] Verify `libx264` is included and functional. Reject a build marked nonredistributable or configured with `--enable-nonfree`; separately check the licenses of every compiled-in external library.
- [ ] Retain upstream notices and copyright material when extracting archives; do not copy only executables and discard accompanying license files.
- [ ] Record provenance for the exact yt-dlp executable and all dependencies embedded in it. Obtain matching sources/build materials for the covered combined executable; the yt-dlp source tarball alone may not contain everything required.

### 2. Review the full Python dependency tree

- [ ] Resolve and lock all direct and transitive Windows dependencies with hashes, rather than relying only on top-level version pins.
- [ ] Inspect the actual wheels for native libraries and license files, particularly PyAV's bundled FFmpeg libraries. Do not classify the complete Python payload as MIT merely because faster-whisper is MIT.
- [ ] Inventory CTranslate2, PyAV, NumPy, Hugging Face Hub, better-profanity, tokenizer/runtime packages, and every additional resolved dependency.
- [ ] For LGPL libraries, document and preserve the applicable replacement/relinking rights and source obligations. For GPL libraries, assess the resulting combined Python program's licensing; do not extend the separate-executable conclusion to in-process linkage.
- [ ] If a dependency combination cannot be distributed under the intended terms, select a compatible build or explicitly resolve the affected program's licensing before packaging.
- [ ] Keep faster-whisper's supported CPU path working without separately downloaded GPU libraries.

### 3. Supply licenses and corresponding source

- [ ] Generate `THIRD_PARTY_NOTICES.md`, a `LICENSES/` directory, and an SBOM from the actual shipped inventory. Preserve full required notices, not just license names or URLs.
- [ ] Clearly state that MIT applies to Expletive Deleted's own code and third-party components retain their respective licenses. Avoid an installer-wide statement implying that everything is MIT.
- [ ] Create a versioned source companion containing the corresponding source required for shipped GPL/LGPL binaries: relevant dependency sources, patches, interface files, and scripts/configuration needed to build/install them. Include a build README explaining the toolchain and commands.
- [ ] Publish that companion next to each installer at no additional charge. Link it from release notes and the app's license information. A generic upstream homepage or GitHub's automatic archive of this app is not a substitute.
- [ ] Retain each release's corresponding source while distributing that release's binaries. Choose this direct source-download approach instead of relying on an informal “email us for source” offer.
- [ ] Review installer/EULA terms for restrictions that conflict with third-party modification, reverse-engineering, or redistribution rights.
- [ ] Provide an accessible About/Third-party licenses view with component versions, full notices, and the release-specific source link. Do not turn routine onboarding into a legal questionnaire.

### 4. Package and locate the runtime

- [ ] Extend `build-audited-runtime.ps1`, `assemble-bundled-runtime.ps1`, staging/manifest generation, and `frontend/electron-builder.yml` to install the reviewed tools and Python packages.
- [ ] Store executable/native resources outside Electron's ASAR archive where required. Include required DLLs and retain complete notice files.
- [ ] Update `backend/runtime/locations.py`, dependency inspection/planning, and Python import configuration to discover the packaged components first under the approved runtime policy.
- [ ] Preserve explicitly configured external-tool paths where supported. Distinguish external components from bundled components in diagnostics.
- [ ] Mark valid bundled dependencies ready without redownloading them. Keep the model download and any repair/download action explicit, cancellable, and verified.
- [ ] Keep installation files immutable during normal use; keep model caches, user settings, and approved updates in the existing per-user locations.
- [ ] Do not silently update bundled yt-dlp/FFmpeg to unreviewed versions. A dependency update must refresh hashes, licenses, source companion, and tests.

### 5. Update release audits and publication

- [ ] Replace blanket “no GPL/processing components” checks with a manifest-based allowlist. Continue rejecting undeclared executables, libraries, wheels, model payloads, and build leftovers.
- [ ] Make CI fail on missing license files, incorrect component versions/hashes, missing source mappings, or an absent source companion.
- [ ] Publish a draft/staged release containing the installer, source companion, notices, SBOM, and checksum file. Verify completeness before making the release public so an installer is not published without its required source.
- [ ] Keep local release scripts and GitHub Actions aligned. Update `AGENTS.md`, the packaging plan, README, QUICKSTART, TROUBLESHOOTING, PROJECT_SUMMARY, and frontend documentation to describe the implemented behavior.

## Validation and acceptance criteria

- [ ] On a clean Windows x64 machine with no system Python/FFmpeg/yt-dlp/Deno, the installed app discovers its bundled runtime without PATH changes.
- [ ] With the approved model cached and networking disabled, transcription and censorship work without downloading Python packages or media tools.
- [ ] Without the model cached, onboarding requests only the remaining required download and explains its size and purpose.
- [ ] Explicitly force `libx264` for a short test encode, then inspect the result with FFprobe to confirm H.264 output. Test on a CPU-only environment so a working hardware encoder cannot hide a broken x264 fallback.
- [ ] Verify normal H.264 conversion, preserve-source behavior, and bundled yt-dlp/Deno integration. Separate deterministic packaging tests from live-site download tests.
- [ ] Test installed paths containing spaces and non-ASCII characters, upgrade behavior, cancellation, and preservation of original media/settings.
- [ ] Inspect the final installer payload, not only its staging directory. Every shipped component maps to notices and, where required, corresponding sources.
- [ ] Verify source-companion extraction and documented build inputs/commands. For an in-house FFmpeg build, perform a clean rebuild and compare functional/configuration results; byte-identical reproducibility is not asserted as a blanket GPL requirement.
- [ ] Run focused backend/packaging tests and the repository's applicable release gates, including native packaged-app smoke testing. Update tests that currently assert the old Python-only policy.

## Separate unresolved release item: H.264/AAC patent coverage

MIT is not the bundling blocker, and changing the application's license to GPL does not eliminate codec patent questions. Free distribution still triggers applicable GPL distribution requirements.

This issue does not assert that a patent agreement is definitely required or that the app is exempt. Before treating the complete release as legally cleared, obtain a project-specific assessment of US/international distribution, free downloads, and the exact codecs shipped. Via LA's public encoder/decoder schedule includes a zero-royalty tier for the first 100,000 units annually, but this does not itself establish an exemption from an agreement or determine how this project's downloads count.

- [ ] Record the maintainer's distribution model and countries, and seek clarification from `info@via-la.com` about AVC/H.264 and AAC coverage, download counting, any applicable royalty tier, and reporting requirements.
- [ ] Have any proposed patent agreement assessed for compatibility with downstream GPL redistribution rights and the actual release. A commercial x264 software license does not automatically settle patents or the rest of FFmpeg's licensing.
- [ ] Record the resulting release decision separately from the engineering checklist. Packaging work can proceed without representing this unresolved item as solved. Do not treat first-run downloads, optional encoding, or platform encoders as proven patent exemptions.

## References

- [FFmpeg licensing and compliance guidance](https://ffmpeg.org/legal.html) — its checklist specifically addresses LGPL library linking; apply the actual selected build's license for this GPL executable bundle.
- [FFmpeg license and external-library rules](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html)
- [GNU FAQ: separate programs and aggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)
- [GPLv2, including source distribution requirements](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)
- [GPLv3, including corresponding source and object-code distribution](https://www.gnu.org/licenses/gpl-3.0.html)
- [yt-dlp executable licensing](https://github.com/yt-dlp/yt-dlp#licensing)
- [faster-whisper license](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) and [PyAV dependency](https://github.com/SYSTRAN/faster-whisper#requirements)
- [x264 licensing](https://www.videolan.org/developers/x264.html) and [commercial licensor's patent discussion](https://x264.org/licensing/)
- [Via LA AVC/H.264 program](https://www.via-la.com/licensing-programs/avc-h-264/) and [AAC program](https://www.via-la.com/licensing-programs/aac/)

## Definition of done

The reviewed Windows installer includes working x264-capable processing tools and Python dependencies, preserves their licenses, has a complete release-specific source companion, and passes packaged-runtime checks. Model downloads remain explicit. The public release's patent assessment/decision is recorded separately; passing packaging tests is not labeled blanket legal clearance.


## Approved phased execution plan

Work one phase at a time. Record changed files, evidence, tests, and open decisions at each gate before advancing. The reviewed input lock specifies approved artifacts; the generated inventory records what was actually assembled. Every output inventory must reconcile with the input lock.

Progress as of September 28, 2026: Phase 0 is approved. Phase 1A and 1B are **in progress, not gate-complete**. Exact tool and wheel candidate manifests plus the evidence and remaining checks are in [the Phase 1 review](../docs/ISSUE83_PHASE1_REVIEW.md). The maintainer chose provisional path A: investigate the published GPL-enabled PyAV wheel with the applicable combined-Python-program obligations, while keeping the project's own source MIT where compatible. An [isolated Python 3.13 local probe](../docs/ISSUE83_PHASE1_LOCAL_PROBE.md) passed imports, synthetic decoding, and offline CPU inference. Candidate hashes and functional tests are not a shipping lock. The selected FFmpeg tool still lacks a complete matched source/build-material map; the CTranslate2 wheel still bundles cuDNN as shipped. Independent Phase 2 contract scaffolding may proceed, but neither phase gate nor an installer distribution-policy change is approved by these candidates.

Phase 1A follow-up: a [yt-dlp PyPI wheel plus EJS candidate](../docs/ISSUE83_YTDLP_WHEEL_PROBE.md) now has source-archive comparisons, exact hashes, third-party JS source anchors, and an offline Python 3.13 version/resource check. It may avoid the separate Python/native payload inside `yt-dlp.exe`, but the expanded wheel/source/notice audit, optional feature coverage, and later desktop adapter remain open. Deno's tagged source archive was also hashed; no Phase 1A gate is marked complete by these checks.

The yt-dlp `pin` dependency expansion has since resolved to 11 PyPI-hash-matched wheels and passed an isolated Python 3.13 offline import/version check. Four wheels contain 46 native files; `mutagen` is GPL-2.0-or-later, and the pinned `idna==3.18` conflicts with the separate 26-wheel candidate's `idna==3.19`. Both generated EJS wheel scripts were reproduced byte-for-byte from the published TypeScript source archive and npm lockfile. The wheel route remains an alternative rather than an approved selection.

The BtbN FFmpeg executable reports 52 enabled external libraries. Its release-tag build scripts and one pinned x264 revision have been identified, but a complete matching source/notice set for that broad payload is not assembled. A narrower pinned GPL FFmpeg/x264/LAME build is the preferred Phase 1A route unless the prebuilt dependency map can be closed. The official CPython 3.13.15 source archive now matches its published checksum; runtime-file and notice mapping remains.

A [local narrow FFmpeg build probe](../docs/ISSUE83_FFMPEG_LOCAL_BUILD.md) now has a hash-checked FFmpeg 8.1.2/x264/LAME 3.100 cross-build with only `libx264` and `libmp3lame` as external libraries. LAME was necessary because audio-only censorship uses MP3. The rebuilt Windows binaries passed synthetic H.264/AAC, MP3 mute, conversion, and preserve-source checks; no processing binary has entered the installer. Exact toolchain snapshot, source/notice companion, static-linkage review, host prerequisites, and the other tools remain Phase 1A work, so the gate is still open.

The existing Python-only release scripts and runtime build-input manifest were updated from pip 25.2 to verified pip 26.2.1 after the Phase 1A review found fixed security issues in the former pin. This does **not** add processing tools to the installer or approve the eventual full input set; pip's vendored notices remain in the Phase 1A/2 audit.

The release's private Python input is now consistently the official, hash-verified full 3.13.15 Windows x64 ZIP in local and CI assembly; the prior Actions toolcache payload remains test-only evidence. A scratch extraction passed the Python-only assembly audit, and the archive includes pip 26.2.1. The narrow FFmpeg recipe also produced a second guarded build and passed H.264/AAC and muted-MP3 probes. These close functional and input-identity questions, not the remaining matching-source/notice and host-prerequisite checks. The maintainer has asked to include the narrow FFmpeg build in the eventual installer; adding it to the current Python-only installer remains gated by the Phase 1B and Phase 2 audits and Phase 3 assembly/audit work unless the approved order is explicitly revised.

Further Phase 1A evidence: [CPython's native-source record](../docs/ISSUE83_CPYTHON_NATIVE_PROVENANCE.md) now maps official Windows external-dependency tags and pip vendored notices; [Deno's record](../docs/ISSUE83_DENO_PROVENANCE.md) identifies its signed binary, locked Rust release recipe, V8 static-library hash, and tagged submodule commits. Neither is a complete third-party notice/license audit. The narrow FFmpeg builder now uses a signed date-pinned Debian snapshot and a [149-package archive/source hash inventory](../docs/ISSUE83_FFMPEG_APT_INPUTS.txt), with a fixed build prefix. Its [fixed-prefix `attempt8` output](../docs/ISSUE83_FFMPEG_LOCAL_BUILD.md) exited cleanly and passed repeatable H.264/AAC, MP3, preserve-source, source-integrity, license/configuration, and import-table checks. Byte-identical rebuilds are not claimed. Phase 1A remains open, so the requested conditional commit has not been made.

### Phase 0 — Distribution policy and scope: approved September 27, 2026

Bundle the processing tools and Python dependency set, including an FFmpeg build with functional `libx264`. Keep the Whisper model as an explicit first-run download. Exclude CUDA/cuDNN and optional GPU runtimes. Keep `preserve_source` as the video default. Treat codec patent review as a separate release gate. This approval supersedes the current Python-only policy for planned work; existing installer behavior remains unchanged until implementation is verified.

### Phase 1A — Processing-tool provenance

- [ ] Identify exact candidate Windows x64 CPython/pip, FFmpeg/FFprobe/x264, yt-dlp/EJS, and Deno artifacts. Record immutable source locations, file hashes, embedded dependencies, build configuration, notices, and corresponding-source/build-material locations.
- [ ] Inspect the selected FFmpeg binary with `-version`, `-buildconf`, `-L`, and `-encoders`; perform a CPU `libx264` encode and verify H.264 with FFprobe. Exclude nonredistributable builds and review every compiled-in external library.
- [ ] Decide from evidence whether upstream FFmpeg/x264 build provenance is complete or an in-house pinned build is required. Check the actual yt-dlp executable's embedded components and corresponding source, beyond the yt-dlp source tarball.
- [ ] Record OS/CPU/runtime prerequisites, download integrity evidence, and any unresolved licensing or source gaps. Retain original archive notices.

Gate: each selected tool has a specific verifiable binary and matching source/license path. An unresolved candidate remains unapproved, with a documented replacement/build decision.

### Phase 1B — Python wheel and native-library review

Local functional evidence: all 26 candidate wheels installed offline into isolated CPython 3.13.15; PyAV and faster-whisper decoded synthetic media, and cached `large-v3` CPU inference completed. The same inference passed when the scratch CTranslate2 cuDNN DLL was temporarily absent and then restored. This supports, but does not approve, an audited no-cuDNN staging transformation. PyAV's oneVPL dispatcher proved required for import; it is distinct from a GPU implementation but must be inventoried. See [the local probe record](../docs/ISSUE83_PHASE1_LOCAL_PROBE.md).

Phase 1B follow-up: the [native-wheel review](../docs/ISSUE83_PHASE1B_NATIVE_REVIEW.md) records a hash-checked, deterministic CTranslate2 wheel transformation that omits only `cudnn64_9.dll` and rewrites `RECORD`. The transformed wheel installed with the other 25 hash-verified wheels under private Python 3.13.15 and passed offline CPU `large-v3` inference. This closes the local cuDNN-omission proof, **not** the Phase 1B gate: PyAV's GPL-enabled native payload, Intel OpenMP/oneMKL notices and redistribution path, `MSVCP140.dll` clean-host handling, and other wheel-native source/notice mappings remain open. No processing package has entered the installer.

- [ ] Resolve every direct and transitive Windows x64 wheel against the pinned release Python version; record filename, wheel tag, source URL, SHA-256, package/version, and dependency edges in a reviewed input lock.
- [ ] Inspect each wheel's metadata, license and notice material, `.pyd`/DLL payload, and bundled native libraries. Include CTranslate2, PyAV's FFmpeg libraries, NumPy, tokenizer/runtime packages, Hugging Face Hub, better-profanity, pip's vendored packages, and other resolved dependencies.
- [ ] Map GPL/LGPL components to corresponding source and any replacement/relinking obligations. Assess in-process Python/native linkage under the intended distribution terms and document compatible substitutions or unresolved decisions.
- [ ] Demonstrate the selected wheels import and the supported CPU transcription path can run with no separately downloaded GPU libraries; record Windows OS/CPU and native runtime requirements.

Gate: the complete selected Python input set is hash-locked, compatible, and accounted for, with a locally proven plan to exclude cuDNN. An unresolved wheel or native library remains unapproved. Auditing the assembled cuDNN-free payload belongs to Phase 3; testing the real installer on clean Windows belongs to Phase 7.

### Phase 2 — Source, notice, and inventory contracts

In progress after checkpoint commit `c5ac7d1`: [Phase 2 contract notes](../docs/ISSUE83_PHASE2_CONTRACT.md), separate v1 input-lock/inventory schemas, a standalone fail-closed validator, and synthetic fixture tests are present. The production generators, source companion, full notice/SBOM content checks, and approved Phase 1 inputs are still missing. This is preparation, not a passed Phase 2 gate or permission to ship candidate binaries.

- [x] Define separate schemas for the approved input lock and the generated shipped-file inventory, with component ownership, source mappings, hashes, notices, and approved transformations. The initial v1 contract and synthetic validator tests are in place; revise only with explicit schema versioning as real approved inputs demand.
- [ ] Build generation and validation tooling for full third-party notices, `LICENSES/`, CycloneDX SBOM, and the versioned source companion. Include source archives, patches, build/install scripts and a build README where required.
- [ ] Define source retention, release links, and installer/EULA review. Test that a missing notice, source mapping, or extra binary fails validation.

Gate: compliance tooling and fixture artifacts validate against the approved Phase 1 inputs. Final artifacts are reconciled with the real payload in Phases 3 and 6.

### Phase 3 — Audited runtime assembly

- [ ] Extend runtime assembly, staging, Electron resource inclusion, generated inventory, audits, and executable verification together. Replace Python-only exclusions with strict lock-based checks while continuing to reject unapproved payloads and models.
- [ ] Assemble the selected tools and Python packages outside ASAR where required, retaining notices, approved DLLs, and immutable installed files. Apply and audit the approved cuDNN exclusion (or CPU-only replacement), including installed metadata and final file inventory. Generate and reconcile notices, SBOM, and source mappings from the assembled contents.
- [ ] Verify native Python imports, tool versions, a CPU-only forced `libx264` encode, and FFprobe inspection of its output.

Gate: a complete staged Windows runtime passes the new audit and executable checks without relying on system processing tools.

### Phase 4 — Desktop runtime integration and migration

- [ ] Update Electron startup and backend resolution so explicitly configured tools, bundled tools, and managed replacements follow a documented precedence; diagnostics show each component's source.
- [ ] Prevent prior per-user Python packages from shadowing or mixing with the reviewed bundled wheel set after upgrade. Keep settings, model caches, and user media intact.
- [ ] Make bundled components ready without redownloads. Keep model download and any repair action explicit, cancellable, and verified. Test fresh installs, upgrades, repair, and the source checkout's separate developer workflow.

Gate: a packaged app uses the intended complete runtime offline with a cached model and requests only the model when it is absent.

### Phase 5 — User-facing license and setup information

- [ ] Add an accessible About/Third-party licenses view with versions, full notices, and the matching release's source-companion link through the typed desktop boundary.
- [ ] Show accurate bundled-versus-download setup status and explain the model's size and purpose before first-run download.

Gate: parent-facing UI and keyboard/theme checks match the actual packaged components.

### Phase 6 — Installer audit and release staging

- [ ] Audit the actual NSIS installer contents as well as `win-unpacked`; reconcile all shipped components with the approved lock, notices, SBOM, source companion, and checksums.
- [ ] Align local packaging and GitHub Actions; create and validate a draft/staged release containing installer, source companion, notices, SBOM, and checksums. Keep public publication after Phases 7 and 8.

Gate: release staging fails closed if any required asset or source mapping is missing, and never publishes the installer alone.

### Phase 7 — Final qualification and documentation

- [ ] On clean Windows x64, install the real NSIS package and test no system Python/FFmpeg/yt-dlp/Deno, model-only onboarding, cached-model offline processing, CPU `libx264`, H.264 conversion, preserve-source behavior, yt-dlp/Deno, cancellation, original-media protection, and paths with spaces/non-ASCII characters.
- [ ] Test upgrades and repair with prior managed components. Run relevant backend, frontend, packaging, and native-app release gates; add regression tests alongside the phase that changes each behavior.
- [ ] Align `AGENTS.md`, the packaging plan, README, QUICKSTART, TROUBLESHOOTING, PROJECT_SUMMARY, and frontend docs with verified behavior. Record the revised policy early without describing unfinished work as shipped.

Gate: the installed app and complete artifact set pass qualification; documentation describes the implemented result.

### Phase 8 — Public-release decision

- [ ] In parallel with engineering work, record distribution countries/model, assess codec patent coverage for the actual shipped H.264, AAC, and MP3 encoder set, and assess any agreement's compatibility with downstream GPL rights.
- [ ] Record a project-specific release decision separately from engineering validation. Only after Phases 6–8 pass should the staged assets become publicly available.

Gate: the maintainer has a documented release decision; engineering tests are not described as blanket legal clearance.

Execution order: **0 approved → 1A → 1B → 2 → 3 → 4 → 5 → 6 → 7 → public-release gate 8**. Phase 8's assessment may start in parallel once the relevant codec inventory is known.
