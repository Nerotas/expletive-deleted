# Issue 83: Deno Windows x64 provenance

Status: **Phase 1A candidate, not release-approved** (September 28, 2026). The existing installer does not contain Deno. This record identifies verifiable source/build anchors; it is not a complete third-party notice audit.

## Binary and tagged build

The selected candidate is [Deno v2.9.6 `deno-x86_64-pc-windows-msvc.zip`](https://github.com/denoland/deno/releases/tag/v2.9.6), 42,601,047 bytes, SHA-256 `15e5300b0ba3c3695a7621d90160a746ec9e710228cee639afa9d580f6e3cd11`, matching the release `.sha256sum`. It contains only `deno.exe` (SHA-256 `2ff9493dfa356be2975f477025ea770088e9e9cb2c83d983236d13561b96b7a6`), with a valid Deno Land Inc. Authenticode signature. Local execution reported Deno 2.9.6, V8 `15.0.245.2-rusty`, and TypeScript `6.0.3`. Its PE import table listed only Windows system DLLs; this is not a complete clean-host test.

The [tagged Deno source archive](https://github.com/denoland/deno/releases/tag/v2.9.6) SHA-256 is `d27f0ec13979c5dc76c7a0f20d5a389041746c005025102c1e220fa034674bbb`. Its MIT `LICENSE.md` is present. `Cargo.lock` SHA-256 is `6c6af74640994cc41fcc7f46bb5204a50da679adc2dee96cb05aa97867baf7e1`; it identifies 1,046 crates.io packages with version/source/checksum and 82 workspace packages. Each registry source is available by its lockfile name/version under `https://static.crates.io/crates/<name>/<name>-<version>.crate`. This is a conservative source universe, not the exact Windows release's compiled subset.

The tagged `.github/workflows/ci.generated.yml` (SHA-256 `6c43e0af841bdcb93fa5fc291dde01223920077ad787e9357757daa3cd06e18d`) specifies Rust 1.95.0, `cargo build --release --locked -p deno ... --features=deno/panic-trace`, code signing, and `deno.exe` ZIP publication. The recipe is evidence of upstream build intent; it does not prove reproducible byte-for-byte linkage to the signed binary.

## V8/static-library source chain

The tagged Deno workspace selects the `v8` crate 150.4.0 (crates.io checksum `42a978ff11f15b24e5c05a7123cf2b68f41e763546699781a924ef4e2cf43a49`) with `simdutf`. The [tagged rusty_v8 build recipe](https://github.com/denoland/rusty_v8/blob/v150.4.0/build.rs) resolves the Windows release input to [`rusty_v8_simdutf_release_x86_64-pc-windows-msvc.lib.gz`](https://github.com/denoland/rusty_v8/releases/download/v150.4.0/rusty_v8_simdutf_release_x86_64-pc-windows-msvc.lib.gz), 39,225,458 bytes; the locally downloaded file matched the release SHA-256 `f231f82cbacb9aefe6d9af57e6df2e8959a40e001f79306485133e3c075b98f0`.

The rusty_v8 v150.4.0 tag tree is Git SHA `5c15a6995c9bb4bacd3e341b59fff32c909c80bf`. Its 20 submodule commit IDs are in [the V8 submodule inventory](ISSUE83_DENO_V8_SUBMODULES.tsv), with upstream repository locations in the tag's [`.gitmodules`](https://github.com/denoland/rusty_v8/blob/v150.4.0/.gitmodules). The main V8 submodule is `denoland/v8` at `ac1e23989121713ca642f6650b34deff7b686896`. GitHub's automatic Deno source tarball does **not** include this external V8/static-library source chain.

The [rusty_v8 tag's `LICENSE`](https://github.com/denoland/rusty_v8/blob/v150.4.0/LICENSE) is MIT. The [pinned V8 submodule's `LICENSE`](https://github.com/denoland/v8/blob/ac1e23989121713ca642f6650b34deff7b686896/LICENSE) is BSD-style and explicitly points to separately licensed embedded code and subdirectory license files. Neither top-level license is a substitute for the remaining submodule and compiled-crate notices.

## Remaining Phase 1A gate

- Resolve the exact Windows-target compiled crate set and each applicable license/notice text. The release ZIP supplies no separate third-party notices. Retain all necessary source archives and notices for the selected binary, not just Deno's MIT file.
- Verify the V8 library's full source/patch/build-material chain and its included third-party licenses against the tagged submodules. The lockfile and submodule map locate inputs but are not a finished source companion.
- Record CPU requirements and confirm the documented host baseline. [Deno's installation guide](https://docs.deno.com/runtime/getting_started/installation/) requires Windows 10 version 1709 or Windows Server 2016 version 1709 and later. The real installer and clean-host behavior are tested in Phases 6-7, not inferred from this local run.
