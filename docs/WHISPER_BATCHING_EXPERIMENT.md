# Whisper batching experiment

## Scope and decision gate

This report records the local performance experiment and its original
recommendation. On November 15, 2026, the product owner explicitly chose batch
size four as the default for fresh desktop transcription despite the unresolved
accuracy and cancellation gates below. Direct CLI transcription remains
standard; compatible existing verified transcripts remain reusable. The model stays
`large-v3`, faster-whisper stays **1.2.1**, and no dependency manifest changes.
There are no downloads, installations, concurrent media transcriptions, or cloud
requests in the experiment.

The initial test uses an explicitly approved local 90-second excerpt. The
supplied existing transcript is a **machine-transcript agreement reference**, not
manually reviewed ground truth. Neither agreement with it nor a faster runtime
is evidence that batching is safe to adopt.

The following thresholds were agreed with the requester before benchmarking:

| Gate | Required result |
| --- | --- |
| Warm speed | At least 20% lower median complete transcription time than standard |
| Censor-word recall | No missed manually labeled censor words |
| False censor detections | No new false detections |
| Boundaries | Every audible word covered; no individual start/end error more than 100 ms worse than standard |
| Cancellation and shutdown | Within 2 seconds of request, original intact |

These are joint gates, not trade-offs. A speed pass alone is not an adoption pass.
The existing desktop's 15-second shutdown grace period is unchanged; the
experiment's stricter two-second gate is not a new product guarantee.

## Hardware and software

Initial hardware inspection on November 10, 2026:

- AMD Ryzen 5 7520U, four physical cores/eight logical processors.
- 16,363,286,528 bytes physical RAM (15.24 GiB).
- AMD Radeon integrated graphics, driver 32.0.11026.1.
- CTranslate2 reports **zero CUDA devices**. Actual inference uses CPU, not the
  integrated GPU; CUDA VRAM measurements are not applicable.
- Requested CPU compute profile: `int8`. The runner records the model's actual
  CTranslate2 device and compute type, which can differ from the requested name.
- Repository virtual environment: CPython 3.14.0, faster-whisper 1.2.1,
  CTranslate2 4.8.1, NumPy 2.5.2, PyAV 18.1.0, huggingface-hub 1.28.0.
- Existing verified local `large-v3` snapshot:
  `edaa852ec7e145841d8ffdb056a99866b5f0a478`.
- Existing FFmpeg/FFprobe 8.0. No processing component was obtained for this test.

No upgrade is necessary to exercise `BatchedInferencePipeline`. This experiment
does not propose one.

## Why batch size 1 is a separate control

The installed [1.2.1 implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
has material pipeline differences even with batch size 1:

- `condition_on_previous_text` is unused and internally set to false.
- `hallucination_silence_threshold` is unused and internally set to `None`.
- Compression-ratio, log-probability, and no-speech failure handling are listed
  as unused arguments.
- Only the first supplied temperature is used, rather than the standard
  temperature-fallback sequence.
- Batched VAD defaults use a 160 ms minimum silence and chunk-limited maximum
  speech duration. Enabling VAD in both modes does not imply identical chunks.

The adapter deliberately does **not** pass unsupported standard options to the
batched path. It retains English, word timestamps, VAD, the same loaded model,
and the same normalized segment/word dictionary shape. Each call creates a
fresh batched wrapper because that wrapper has mutable timestamp state.

Compare standard versus batch 1 for the pipeline change, then batches 2 and 4
versus batch 1 for throughput gains. Larger batches are not part of this initial
CPU screen.

## Reproducible runner

From the repository root, after closing the desktop and other processing jobs:

```powershell
$folder = 'tmp\Issue-93-media\SucculentMeal'
$source = Get-ChildItem -LiteralPath $folder -Filter '*.mp4' -File | Select-Object -First 1
$reference = Get-ChildItem -LiteralPath $folder -Filter '*.json' -File | Select-Object -First 1
.\.venv\Scripts\python.exe -m scripts.benchmark_whisper `
  --source $source.FullName --reference $reference.FullName `
  --output 'tmp\whisper-batching-new-run' `
  --start 0 --seconds 90 --repeats 3 --mode-timeout 2400
```

The runner is intentionally Windows/CPU-only for this hardware qualification.
It refuses a conflicting CUDA override and checks the exact faster-whisper
version. Other hardware needs a separate qualification; this is not a GPU
benchmark implementation.

The runner:

1. Requires an entirely new output directory; it cannot overwrite an existing
   experiment, the source, or a cached transcript.
2. Uses the existing desktop-profile ownership lock to exclude another runner
   or the desktop using that profile. Close processing in other profiles too.
3. Pins and hashes the source through the existing verified-source read lease,
   and checks its SHA-256 again afterward.
4. Prepares one mono 16 kHz PCM excerpt locally, selecting the first audio stream.
   Recognized 5.1/7.1 layouts use the same `pan=mono|c0=FC` front-center filter as
   production. The supplied clip is stereo, so this does **not** qualify surround
   behavior.
5. Runs standard, batch 1, batch 2, and batch 4 sequentially. Each mode gets a
   fresh worker/model, an initial full transcription, then three warm runs using
   that resident model. Initial runs are excluded from warm medians. Mode order
   is fixed, not randomized: thermal drift/order bias remains a limitation.
6. Times model construction separately. Transcription timing starts before
   `transcribe_segments` and ends only after consuming the entire lazy iterator:
   it includes audio decode, VAD/features, inference, and word alignment, not
   merely generator construction. Excerpt preparation is recorded separately;
   censor encoding, source hashing, and transcript persistence are excluded.
   "Cold load" means a new process/model, **not** a flushed OS disk cache.
7. Samples worker working set, private commit, and whole-system physical usage
   every 100 ms using Windows native APIs, with no monitoring dependency.
   Per-run sampled peaks can miss sub-100 ms spikes. The OS process-lifetime
   working-set high-water mark is also recorded, but is cumulative and must not
   be presented as an independently reset warm-run peak. Whole-system usage
   includes unrelated applications.
8. Records segment arrival times and the largest progress gap, including the
   initial wait. Segments arriving together are not smooth realtime progress.
9. After the measured runs, starts another real transcription and requests
   cooperative cancellation one second after entry. Checkpoints run before
   preparation, before advancing the iterator, and after native decoding.
   They cannot interrupt native inference or eager VAD/preparation. A worker
   still running after two seconds is forcibly terminated and the gate fails;
   forced cleanup is **not** reported as cooperative responsiveness. This
   request timing does not prove which native stage was active.
10. Preserves completed measurements, reports errors without fallback/retry, and
    uses a new process for the next mode. Ctrl+C/timeout terminates the current
    worker. There is no experimental censored output or production transcript
    that could be partially published.

The worker loads only the verified local model with `local_files_only=True` and
offline Hugging Face environment flags. The adapter bypasses transcript lookup
entirely, so every measurement performs fresh inference. It does not update the
application's transcription-speed calibration.

`summary.json` and individual run JSON files contain local transcripts and
potentially sensitive dictionary entries; leave them in the ignored experiment
directory. They are diagnostic experiment artifacts, not valid production
transcripts and must not be copied into the app's transcript directory.

## Accuracy and audible-review protocol

The optional existing transcript permits only an agreement screen:

- Snapshot the current configured censor words minus exclusions; do not mutate
  the dictionary or substitute the broad vendor list.
- Match normalized censor words one-to-one to the nearest same-token reference
  occurrence within one second. Missing and unmatched occurrences are reported
  separately; repeated occurrences cannot reuse one detection.
- Report recall, absolute start/end errors, and whether the production-default
  150 ms padding covers the reference interval.
- Compare start/end error **per reference occurrence** against standard. Comparing
  only the maximum errors of two runs can hide an individual regression.
- Never call unmatched detections "false positives" without manual review.
  Settings-specific padding, stereo karaoke effectiveness, rendered sound, and
  words with missing timestamps require separate review.

Before any adoption decision, assemble a manually reviewed corpus covering clear
dialogue, background noise/music, quiet speech, long silences, surround dialogue,
and censor words spanning or adjacent to **actual VAD chunk boundaries**. Do not
assume every 30-second position is a chunk boundary. Review enough context on
both sides of each split to assess lost previous-text conditioning.

Annotate every intended censor occurrence with audible start/end times, policy
decisions, non-censor lookalikes, silence regions, and the coverage category.
Listen to every proposed censored boundary with the real saved padding/output
method; mark residual audible phonemes and unnecessarily removed dialogue.
Check silence regions for invented words, not just censor words. Missing word
timestamps must fail this review rather than relying on evenly spaced fallback
word times.

The current clip/reference cannot certify those requirements. A supplied
machine transcript has no independent guarantee of correct censor words,
timestamps, silence labels, or chunk-boundary coverage.

## Results

### Local speed screen: November 10, 2026

The approved source is a 399.061-second stereo video in the local
`tmp/Issue-93-media/SucculentMeal/` directory. Only seconds **0-90** were tested.
Excerpt preparation took 0.313 seconds, outside the inference timer. All modes
actually used CTranslate2 **CPU / int8_float32**, despite requesting the `int8`
profile. Each mode completed its initial run and all three warm repetitions.
There were no inference exceptions or observed out-of-memory failures.

| Mode | New-model load (s) | Initial transcription (s) | Warm runs (s) | Warm median (s) | Time reduction vs standard |
| --- | ---: | ---: | --- | ---: | ---: |
| Standard | 25.651 | 194.555 | 213.144, 198.038, 191.730 | 198.038 | baseline |
| Batch 1 | 18.739 | 106.509 | 105.842, 103.537, 101.342 | 103.537 | 47.72% |
| Batch 2 | 16.873 | 97.849 | 98.797, 97.855, 98.389 | 98.389 | 50.32% |
| Batch 4 | 15.432 | 106.070 | 100.502, 94.067, 95.319 | 95.319 | 51.87% |

All three experimental modes pass the **speed-only** 20% gate. Most of the
reduction already occurs at **batch 1**: it cannot be attributed to parallel
batching alone. Batch 2 saves another 4.97% versus batch 1; batch 4 saves 7.94%
versus batch 1.

Post-run reconstruction using the identical excerpt and installed batched VAD
defaults produced just **three** merged chunks (29.312, 29.648, 21.8165 seconds
of speech). Thus `batch_size=4` processed at most **three** chunks together; this
is a cap-4 measurement, not evidence about a fully occupied four-chunk batch.
Reconstruction was outside the measured runs and did not instrument inference.

### Memory and progress

All memory values below are **GiB**, not GB. Working-set peaks include the
initial run; warm RSS/private/system columns are sampled maxima over all three
warm runs.

| Mode | OS lifetime peak worker RSS | Peak warm sampled worker RSS | Peak warm private commit | Peak sampled whole-system physical use |
| --- | ---: | ---: | ---: | ---: |
| Standard | 2.629 | 2.584 | 2.988 | 14.843 |
| Batch 1 | 2.698 | 2.305 | 2.662 | 14.236 |
| Batch 2 | 3.115 | 2.879 | 3.163 | 14.641 |
| Batch 4 | 3.412 | 3.317 | 3.714 | 15.235 |

The machine has only 15.24 GiB physical RAM. It was under substantial
whole-system memory pressure, nearly full at the batch-4 peak. Working set can
shrink under paging, so a lower sampled RSS must not be interpreted as lower
allocation demand. Background applications were not controlled or terminated.
These are real measurements on this laptop, not isolated laboratory results or
claims about other CPUs/GPUs. Do not try larger batches here based on this run.

Worst warm segment-progress gaps were 68.189 seconds (standard), 44.202 seconds
(batch 1), 69.225 seconds (batch 2), and **100.501 seconds** (batch 4). Batch 4
effectively withheld progress until nearly the whole transcription was finished.
There were no missing-word-timestamp segments in any of the 16 completed runs.

### Censor-word agreement, not verified accuracy

The existing full-video transcript contains ten configured censor occurrences
fully within the excerpt. Its original word times and content have **not** been
manually confirmed, and cropping can itself change end-of-excerpt recognition.
The following results must not be presented as measured real-world accuracy:

| Mode | Matched reference occurrences | Unmatched reference occurrences | Unmatched detections | Maximum error of matched word boundaries |
| --- | ---: | ---: | ---: | ---: |
| Standard | 9/10 | 1 | 0 | 20 ms |
| Batch 1 | 5/10 | 5 | 1 | 30 ms |
| Batch 2 | 5/10 | 5 | 1 | 30 ms |
| Batch 4 | 5/10 | 5 | 1 | 30 ms |

All repeated outputs within each mode were identical. The batched modes had the
same recognized word sequence; batch 2 differed from batch 1 by up to 20 ms in
individual timestamps. Standard yielded 208 word records; batched modes yielded
199. This is a pipeline-behavior change already visible at batch 1, not a
batch-size-dependent recognition difference in this sample.

Among matched occurrences, 150 ms padding covered the reference times and the
largest additional boundary error versus standard was 30 ms. **That does not
clear the boundary gate:** unmatched occurrences are excluded from that small
number. For example, a same-token batched candidate starts at 52.09 seconds
versus a reference occurrence at 53.74 seconds, outside the one-second matching
window. It needs listening review to distinguish a recognition change from a
large timestamp error; missing/unmatched targets must not be hidden by quoting
only the good matched-word timestamps.

No manually labeled silence/hallucination evaluation, surround evaluation,
actual-chunk-boundary reference review, or listening review of rendered
censorship was performed. The observed agreement regression is a reason to
**stop short of adoption**, not proof of exactly five genuinely missed audible
words or one genuine false detection.

### Cancellation, shutdown, and recovery

Every mode remained in processing beyond two seconds after the cooperative
request. All required explicit termination of the disposable worker:

| Mode | Request to terminated worker (s) | Two-second cooperative gate |
| --- | ---: | --- |
| Standard | 2.197 | fail |
| Batch 1 | 2.215 | fail |
| Batch 2 | 2.177 | fail |
| Batch 4 | 2.241 | fail |

These times include termination/join overhead after the two-second deadline.
They are **not** natural cancellation latencies. The next mode successfully
loaded a fresh real model after each preceding forced termination. Worker
shutdown, timeout cleanup, explicit memory-error reporting, and subsequent
worker recovery also have regression coverage. Windows pipe closure initially
surfaced `BrokenPipeError` in the lifecycle tests; the runner now handles that
specific EOF condition while retaining unexpected exit/error diagnostics.

The full source SHA-256 remained unchanged. No production transcript, output
media, calibration, or model cache was overwritten, and no experimental result
was published to the desktop queue. Profile-exclusion hardening and additional
post-run scoring were added during implementation; timings were not rerun
after those non-inference changes. The measured workers were sequential; this
screen does not establish that background system load was absent.

### Original recommendation (before the product decision)

**Retain standard inference. Do not enable batching by default or expose it as a
parent-facing processing option yet.**

The local speed gain is meaningful, but censor-word agreement regressed
substantially and the agreed cancellation gate failed. Accurate audible
boundaries, silence handling, and six-category coverage remain unverified.
The current result is therefore **speed pass, cancellation fail, accuracy
acceptance blocked with a concerning agreement signal**.

Continue only as a separate reviewed experiment: label the missing/unmatched
occurrences by listening, add the six-category corpus, capture actual chunk
boundaries, and repeat under lower memory pressure. Batch 1 should remain the
pipeline control; do not start by increasing batch size or upgrading dependencies.
Interruptible native processing would need its own carefully scoped lifecycle
design before any two-second desktop cancellation claim.

The desktop now selects batch size four for fresh transcription. Settings, cache
verification, source archival rules, downstream censoring, and the shared
transcription/censoring slot remain unchanged. The product decision does not
change the measured results or establish that the previously unmet gates passed.

## Validation and local artifacts

- Focused adapter/profile/lifecycle regression suite passed (28 tests).
- Final full backend suite passed (**410 tests**), including the additional
  busy-profile exclusion and ownership-release checks.
- Editor diagnostics reported no errors in the changed Python files;
  `git diff --check` passed.
- The runner was exercised on actual approved media: 16 completed full
  transcriptions plus four real cancellation probes.
- No renderer/Electron code changed; frontend build/smoke and a new native
  desktop UI run were not performed. Backend process-lifetime/job tests do not
  qualify experimental batching inside Electron.
- Local detailed results, normalized outputs, progress traces, excerpt,
  checksums, and test logs are retained in the ignored
  `tmp/whisper-batching-2026-11-10/` directory. Do not upload it as a public report.
