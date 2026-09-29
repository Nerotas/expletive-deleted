# Issue 83: CPython Windows input provenance

Status: **Phase 1A candidate, not release-approved** (September 28, 2026). The installer still carries only the private Python bootstrap runtime. The same official full runtime archive is now selected for local and CI assembly; this record does not approve processing-tool bundling.

## Selected archive and local check

The private runtime input is [Python 3.13.15 Windows x64 full ZIP](https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.zip), 34,324,622 bytes, SHA-256 `6479223746cdfb79d25865110d6f524ac98de081324e119af1dc3ae36bddc7a5`. It is not the smaller embeddable package. `python.exe` and `python313.dll` had valid Python Software Foundation Authenticode signatures. A scratch extraction reported Python 3.13.15 and pip 26.2.1; the bundled `Lib/ensurepip/_bundled/pip-26.2.1-py3-none-any.whl` hashes to `71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e`, matching the selected published pip wheel. The existing Python-only runtime assembly/audit passed outside the sandbox and hashed 3,766 payload files. A sandbox-only Node subprocess launch returned `EPERM`; that run is not evidence of a payload failure.

The [official source tarball](https://www.python.org/downloads/release/python-31315/) SHA-256 is `1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76`. Its `PCbuild/get_externals.bat` names the source and prebuilt dependency tags below. The Git commit IDs were resolved from the corresponding `python/cpython-source-deps` and `python/cpython-bin-deps` refs; two annotated source tags were dereferenced to the underlying commits. These refs establish immutable locations for CPython's Windows build inputs, but do not prove by themselves that each DLL in the published ZIP came from the tagged input without modification.

The [pip 26.2.1 source archive](https://pypi.org/project/pip/26.2.1/) SHA-256 is `f6ad667e89a1fe78046c8f13232b247200f5258d7828f3f7883d660878e0813f`; all 450 `pip/` wheel files matched the published source archive byte-for-byte in the earlier probe. Its vendored `vendor.txt` names exact versions for CacheControl, distlib, distro, msgpack, packaging, platformdirs, pyproject-hooks, requests/certifi/idna/urllib3, rich/pygments, resolvelib, setuptools, tomli, tomli-w, and truststore. The wheel and full Python ZIP retain their individual vendored license paths and no pip native DLL/PYD. The vendored source in the pip sdist is the corresponding pure-Python source; Phase 2 must include each applicable notice text, not summarize the entire pip payload as MIT alone.

| Source-dependency tag | Git commit |
| --- | --- |
| `bzip2-1.0.8` | `05301997b2f9590f49c672cf3dfd3d3dfa7ad521` |
| `libffi-3.4.4` | `73b247f34ef3ae1859b8c2c34d321d34ebc5db15` |
| `openssl-3.0.21` | `460451a0bb19cdbf0ab1add4de1420d143995467` |
| `mpdecimal-4.0.0` | `48316ec025c1ebe500854c332be0a12c640c7301` |
| `sqlite-3.50.4.0` | `ef547e549b49a2822214ef7880c0ca212b32929e` |
| `tcl-core-8.6.15.0` | `275286594fd3e162af29e8c0ba4e365d3d1f7775` |
| `tk-8.6.15.0` | `a526badcf885e4986e13e68695398a0bb64d5ea1` |
| `xz-5.2.5` | `c6bc0c612605622aaef101a33a751f9de2ecc193` |
| `zlib-1.3.1` | `4dc98e1909830e2bdc2a9cc2236e3c5d5037335b` |

| Binary-dependency tag | Git commit |
| --- | --- |
| `libffi-3.4.4` | `94cb9a1c7feb608adf2b9f8fe2dbd6925ffbf90d` |
| `openssl-bin-3.0.21` | `4c7747da0d1addd20c95c2f911f8d2e09254a3d2` |
| `tcltk-8.6.15.0` | `5a51bb7b87efa119332c52b04a84c49d3042279c` |
| `nasm-2.11.06` | `e544f0d859280f29d29c6ada34ec7b49ca4db325` |

Observed DLL versions in the ZIP agree with OpenSSL 3.0.21, SQLite 3.50.4.0, Tcl/Tk 8.6.15, and zlib 1.3.1. It also contains `libffi-8.dll`, Microsoft `vcruntime140.dll`/`vcruntime140_1.dll` version 14.51.36247.0, and other Python extension modules. Preserve the archive's root `LICENSE.txt`, Tcl/Tk `license.terms`, pip's complete `dist-info/licenses/` and vendored license files, rather than carrying only two summary license labels.

The exact external-source tag trees place notices at `bzip2/LICENSE`, `libffi/LICENSE` and `LICENSE-BUILDTOOLS`, `openssl/LICENSE.txt`, `mpdecimal/COPYRIGHT.txt`, `tcl-core/license.terms`, `tk/license.terms`, `xz/COPYING` plus its GPL/LGPL-specific files, and `zlib/LICENSE`. The SQLite tag is an amalgamation without a root license file; [SQLite's own copyright page](https://www.sqlite.org/copyright.html) identifies its deliverable code as public domain. These locations are discoverable source anchors, not evidence that all relevant text has been copied into the current installer.

The included Microsoft VC runtime DLLs need their own treatment. [Microsoft's Visual Studio 2026 redistribution list](https://learn.microsoft.com/en-us/visualstudio/releases/2026/redistribution) identifies the Visual C++ runtime folder as distributable **subject to Visual Studio license terms and a validly licensed copy**; [Microsoft's deployment guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170) permits app-local DLL deployment but cautions about servicing. This is a terms/location anchor, not a claim that this project has independently established its Visual Studio redistribution entitlement. That project-specific check belongs before public release.

## Still required at the Phase 1A gate

- Download/hash or otherwise immutably map the exact source packages, binary-input repositories, native DLLs, Microsoft runtime terms, and all applicable notice texts. The ZIP's top-level `LICENSE.txt` alone is not a full inventory of all included native components.
- Reconcile the runtime's actual files with the selected source/notice paths and the pip vendored dependency list. The Phase 2 generator will carry those texts into release notices; Phase 3 will reconcile the staged payload.
- Record the supported host/CPU range. [CPython's Windows documentation](https://docs.python.org/3.13/using/windows.html) states Windows 8.1+, while the selected Deno runtime sets a higher Windows 10/Server 2016 version 1709 floor for the complete future bundle. Clean-host qualification belongs to Phase 7.
