# Issue 83 Phase 2 — source, notice, and inventory contract

Status: **started, not gate-complete**. Phase 1 has not approved a processing payload. The schemas and validator here are isolated preparation; they do not replace the current Python-only runtime manifest or audit.

## Two different records

The reviewed [input-lock v1 schema](schemas/issue83-input-lock-v1.schema.json) records the *intended* Windows x64 release inputs. It requires an explicit `approved` status; a release ID; each component's version and license expression; exact payload, source, notice, and license artifacts with HTTPS origin and SHA-256; and named, approved transformations. An artifact extracted from another archive additionally records `origin_artifact_id` and `archive_member`; its URL must equal the hashed parent archive's URL. Each component must have a selected payload and source/notice/license artifacts. A build transformation must identify both source and build-script inputs. The Phase 1 [tool](ISSUE83_TOOL_CANDIDATES.json) and [wheel](ISSUE83_WHEEL_CANDIDATES.json) manifests are **not** this lock and must not be relabeled approved.

The generated [shipped-inventory v1 schema](schemas/issue83-inventory-v1.schema.json) records what an assembly *actually* produced. Its `input_lock_sha256` binds the record to the exact UTF-8 bytes of the approved lock. Each file has a scope (`installer` or extracted `source` companion), relative path, SHA-256, purpose, owning component, transformation, and input-artifact references. Generated release-wide metadata may use the reserved owner `release` and a `generate` transformation. Runtime files require component ownership; source archives, patches, and build scripts require the `source` scope; notices/licenses require the `installer` scope.

The [standalone contract validator](../scripts/issue83_contract.py) checks strict fields and cross-references, case-insensitive duplicate paths, component ownership, the required source/notice/license and payload presence, copy hashes, and an exact filesystem-to-inventory match. Symlinks, traversal paths, extra files (including binaries), missing files, and mismatched hashes fail. It requires separate extracted installer and source-companion roots:

```powershell
.\.venv\Scripts\python.exe scripts\issue83_contract.py `
  --input-lock path\to\approved-input-lock.json `
  --inventory path\to\generated-inventory.json `
  --installer-root path\to\unpacked-installer `
  --source-root path\to\extracted-source-companion
```

Only synthetic fixtures are currently used to test this command's contract. It cannot turn the Phase 1 candidates into approved inputs, and no real Issue 83 installer or source companion exists. The validator is not yet wired into the production build or release workflow; that belongs to later phases after input approval.

## Remaining Phase 2 work

- Generate the inventory from the real assembled payload, not by copying planned filenames. Verify downloaded/staged input artifact hashes, archive members (including embedded notices), and member hashes before transformation; record every transformation's actual output.
- Generate complete `THIRD_PARTY_NOTICES.md`, `LICENSES/`, and CycloneDX SBOM from the approved component data and actual inventory. License identifiers and notice filenames alone are insufficient; preserve the full required texts and upstream copyright notices. Add validation for their content and version/component consistency.
- Build a versioned source companion containing exact corresponding source archives, applicable patches, interface files, and build/install scripts/configuration, with a README giving the toolchain and commands. Validate the produced archive, not just its extracted test directory.
- Make the release retain a matching source companion, notices, SBOM, checksums, and installer together for each distributed version. Keep the companion available while that binary release is distributed and for any additional period required by the selected licenses. Release notes and the app's license view must link to the *matching release*, not a generic project homepage.
- Review installer/EULA wording against the actual selected licenses for restrictions on modification, reverse engineering, and redistribution. This is a release gate, not a conclusion that the current candidate set is compliant.

The Phase 2 gate stays open until the generator, source-companion builder, content checks, and synthetic fail-closed fixtures validate against **approved** Phase 1 inputs. Phases 3 and 6 must then reconcile the real runtime and installer against these records.
