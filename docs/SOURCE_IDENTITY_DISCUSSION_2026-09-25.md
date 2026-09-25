# Source identity: discussion and initial benchmark — September 25, 2026

**Status: source identity implemented after the owner explicitly requested implementation. Legacy migration remains deferred.** The earlier benchmark-only authorization was followed by an implementation request. Existing media and legacy artifacts are not renamed, adopted, or regenerated automatically.

The issue supplied in the discussion was called HP-07. In the repository's [decision register](HIGH_PRIORITY_ISSUES_AND_DECISIONS_2026-09-17.md#hp-05-source-identity-and-legacy-artifacts--deferred) and [repair plan](HIGH_PRIORITY_REPAIR_PLAN_2026-09-17.md#hp-05-deferred-source-identity-and-legacy-migration), source identity is HP-05; HP-07 covers destination containment. This note follows the supplied source-identity scope without renumbering either issue.

## Identity method

Use SHA-256 over the entire original file and retain the full digest. File size, duration, filename, modification time, and partial-file sampling must not substitute for content identity. SHA-256 is a collision-resistant cryptographic hash, not a guarantee that collisions are mathematically impossible. See [NIST hash-function guidance](https://csrc.nist.gov/Projects/Hash-Functions/NIST-Policy-on-Hash-Functions).

- Identical bytes have the same content identity after a rename, relocation, or copy. Paths still describe distinct file locations.
- Different contents, including same-length replacements, are expected to produce different digests with overwhelming confidence.
- Container metadata edits, remuxing, and re-encoding change byte identity. Transcript reuse across these changes needs a separate compatibility policy; a hash mismatch alone must not automatically trigger retranscription.
- A matching source digest establishes content identity, not model/settings compatibility, transcription accuracy, or whether a finished copy reflects the current censor policy.

## Artifact relationships and naming

New transcript JSON stores the original media's full digest and byte count alongside text, words, and model metadata. The digest is authoritative; the byte count supports diagnostics and quick rejection, never acceptance on its own:

```json
{
  "source_identity": {
    "algorithm": "sha256",
    "digest": "<full SHA-256 of the original media>",
    "size_bytes": 1862791159
  }
}
```

Record relationships when artifacts are created. The transcript and finished media contain different bytes from the original; their own hashes will not equal the source hash.

| Artifact | Recorded relationship |
| --- | --- |
| Original media | Full source SHA-256; separately tracked locations |
| Transcript | Source SHA-256 and transcription model/settings |
| Finished copy | Source SHA-256, hash of the transcript used, and censoring/output settings |

Transcript names include the complete input filename: `movie.mp4-transcript.json` and `movie.mkv-transcript.json`. Censored output names omit the source container, such as `movie-censored.mkv`; prior full-filename outputs such as `movie.mp4-censored.mkv` remain recognized and are not renamed or deleted. Relative input folders are preserved. Because two same-stem source files in one folder would share an output name, censor submission rejects that collision until one source is renamed. Names locate artifacts; hashes establish content identity.

Finished copies have a `<output filename>.provenance.json` companion with `schema_version: 1`, `source_identity`, `transcript_sha256`, `output_sha256`, and `processing`. The transcript and output hashes cover their exact complete bytes. Processing records include the model/library, censor method, padding, video/audio settings, include-undiscovered choice, and the censor/exclusion lists used. These records stay local. The transcript's own hash is stored in output provenance, avoiding self-reference.

Media and metadata are each published through guarded staging. A crash between their publications can leave saved media with missing or stale provenance. No original is archived after that failure. Explicit playback checks the output hash and source identity; incomplete records cannot authorize it. Explicit Recensor can replace the saved copy and rebuild provenance. Prior transcript bytes are retained in a content-addressed `.history` file before an explicitly requested replacement. No source media is copied or altered to compute identity.

## Verification schedule

| Event | Behavior |
| --- | --- |
| Application startup, library refresh, queue polling | Read existing records; do not hash the collection |
| First transcription job | Hash the selected source to establish identity |
| Later job reusing a transcript | Re-hash the source before accepting the cached transcript |
| Transcription immediately followed by censoring in a single CLI/batch job | One verification under the same source lease; separately queued desktop stages each verify again |
| Matching a renamed or relocated source | Hash when establishing that mapping, not automatically during browsing |
| Explicit playback, transcript review, or archival | Verify source identity before accepting the recorded relationship; playback also hashes the output |
| Suspected source change | Verify before further artifact reuse |

Strong verification across separate jobs requires reading the whole source again. Unchanged size and timestamps cannot prove unchanged contents. Re-hashing is separate from retranscription: a matching digest permits reuse only when the other compatibility checks also pass.

The existing Windows read lease denies ordinary writes and replacement throughout hashing and processing. Hashing uses 1 MiB chunks, checks cancellation between reads, and emits percentage progress as **Checking source contents**. Queue rows describe recorded state; they do not claim that polling has freshly verified content. Metadata checks during polling can reject obviously incompatible records but cannot prove current content identity.

A transcript job for a renamed or relocated original can search the configured transcript root for a uniquely matching fingerprinted, compatible transcript after hashing the source. It writes a new association at the current artifact path while preserving the prior transcript. Different matching transcripts stop for review. Finished copies are not relocated automatically. Legacy transcripts without fingerprints are excluded from matching.

An unidentified or mismatched transcript stops processing; it never silently invokes Whisper. The owner can explicitly choose **Retranscribe**, or retain the artifacts for later manual mapping. Legacy rows show **Needs review**, with bulk processing, playback, and archival disabled. CLI users can explicitly request `--force-transcribe`; output replacement remains a separate `--overwrite` action.

## Initial performance evidence

The selected input was one existing finished MKV copy, opened read-only. Its size was **1,862,791,159 bytes (approximately 1.735 GiB)**. Media paths, titles, and the content digest are intentionally omitted from this repository note.

| Measurement | Seconds | MiB/s |
| --- | ---: | ---: |
| PowerShell/.NET SHA-256, initial agent run | 1.790360 | 992.26 |
| PowerShell/.NET SHA-256, owner-reported run | 1.860999 | 954.59 |
| Python `hashlib.sha256`, 1 MiB chunks | 2.4397 | 728.15 |
| Python `hashlib.file_digest`, SHA-256 | 1.4214 | 1249.79 |

All four reported the same complete digest. Timers covered opening, reading, hashing, and closing the file, excluding shell/interpreter startup. No transcription ran and no media content was written. Python measurements used the repository environment: CPython 3.14.0 with OpenSSL 3.0.18.

These are individual runs, potentially benefiting from Windows caching, not a controlled comparison of implementations. The first run is not proven to have been a cold read. The storage device type was not established. No representative original, external-drive, collection-scale, or disk-impact qualification has been completed, and originals were not fingerprinted or mapped to this finished copy.

The owner considered the timing concern substantially reduced after the 1.86-second result. It supports continuing the SHA-256 design discussion, without establishing a universal processing-time estimate.

### Repeat the standalone benchmark

From the repository root, substitute a file you choose:

```powershell
.\scripts\measure_file_sha256.ps1 -Path 'E:\Movies\Feature Film.mkv'
```

Optional `-Runs 3` measures three separate complete reads. Subsequent reads may benefit from caching. The script prints the digest, size, elapsed seconds, and throughput; it opens the media read-only, writes no sidecars, and does not change application behavior or install dependencies. Selecting a network path reads from that location. It uses bounded memory and allows other readers while denying ordinary writes/deletion during its read.

The script was validated on Windows PowerShell 5.1 against `Get-FileHash`, repeated runs, byte counts, directory rejection, and missing-file rejection. That benchmark remained separate from application integration. The subsequent implementation adds regression tests discovered by the existing backend/frontend CI and extends native Electron smoke coverage; there are no expected-failure gates.

## Python implementation

The backend uses standard-library `hashlib` with SHA-256; no hashing dependency was added. `hashlib.file_digest` requires Python 3.11 or later. Chunked `hashlib.sha256().update()` supports the project's Python 3.9 minimum and offers opportunities for progress and cancellation checks between chunks. The implemented chunked reader uses 1 MiB buffers. Both approaches compute the same digest; larger-media and external-drive performance remains subject to representative measurements. See [Python hashlib documentation](https://docs.python.org/3/library/hashlib.html).

## Validation and remaining qualification

Validated on Windows on September 25, 2026: all **361 backend tests** and **208 frontend tests** passed, along with frontend typecheck, lint, and build. Standard Electron smoke and native file smoke passed. The Needs review state was visually inspected in light/dark themes at 1060 and 1440 pixel widths. `git diff --check` passed. No real media was transcribed, transcoded, migrated, or archived during implementation validation; processing and failure scenarios use synthetic fixtures.

Regression coverage includes known SHA-256 vectors, cancellation during hashing, same-size replacements with preserved timestamps, Windows source write/rename denial, per-job verification and nested reuse, unique/ambiguous renamed-file matching, explicit legacy retranscription preserving old bytes, transcript history, output tampering, interrupted provenance publication and retry, and no hashing during library polling. Frontend coverage checks the Needs review restrictions and explicit retry/retranscription actions. Native Electron smoke exercises that state in light/dark themes at 1060 and 1440 pixel widths; native playback smoke uses real source/output fingerprints.

Representative original-media and external-drive performance, whole-collection disk impact, and real codec/model hardware qualification remain manual work. Metadata adds JSON companions and retained transcript history; it does not duplicate originals for identification. History is retained rather than automatically pruned.

A preview-and-confirm legacy mapping tool remains future work. A fingerprint taken today cannot establish which source generated an old transcript or finished copy. No blanket regeneration or automatic legacy adoption is approved. Publication collision protection alone does not resolve identity; the new digest checks enforce the relationship for fingerprinted artifacts.
