"""Offline Windows-only Whisper experiment; never writes production transcripts."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
import traceback
from typing import Any

from backend.censor.media import has_discrete_center_channel
from backend.filesystem.locking import StoreBusyError
from backend.media_identity import hash_stream, verified_source
from backend.policy import PolicyStore
from backend.runtime import find_ffmpeg, find_ffprobe
from backend.runtime.devices import get_whisper_device_status
from backend.runtime.transcription import load_transcription_model, transcribe_segments
from backend.settings import SettingsStore


THRESHOLDS = {
    "minimum_warm_speedup_percent": 20,
    "maximum_missed_censor_words": 0,
    "maximum_new_false_censor_detections": 0,
    "maximum_additional_boundary_error_seconds": 0.1,
    "maximum_cancellation_seconds": 2,
}
MODES = (None, 1, 2, 4)


@contextmanager
def experiment_slot():
    with ExitStack() as resources:
        try:
            resources.enter_context(SettingsStore().desktop_owner())
        except StoreBusyError as exc:
            raise RuntimeError("Close the desktop app and other benchmarks for this profile before measuring Whisper.") from exc
        yield


def mode_name(size: int | None) -> str:
    return "standard" if size is None else f"batch-{size}"


def write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class WindowsMemory:
    """Sample working set/private commit without installing a monitoring package."""

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
            ("peak_rss", ctypes.c_size_t), ("rss", ctypes.c_size_t),
            ("peak_paged", ctypes.c_size_t), ("paged", ctypes.c_size_t),
            ("peak_nonpaged", ctypes.c_size_t), ("nonpaged", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
            ("private", ctypes.c_size_t),
        ]

    class Status(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.DWORD), ("load", wintypes.DWORD),
            ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
            ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
            ("extended", ctypes.c_ulonglong),
        ]

    def __init__(self, pid: int):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(self.Counters), wintypes.DWORD,
        ]
        self.kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(self.Status)]
        self.handle = self.kernel.OpenProcess(0x410, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def sample(self) -> dict[str, int]:
        counters = self.Counters()
        counters.cb = ctypes.sizeof(counters)
        status = self.Status()
        status.length = ctypes.sizeof(status)
        if not self.psapi.GetProcessMemoryInfo(self.handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "rss_bytes": counters.rss, "private_bytes": counters.private,
            "process_lifetime_peak_rss_bytes": counters.peak_rss,
            "system_used_bytes": status.total - status.available,
            "system_total_bytes": status.total,
        }

    def close(self) -> None:
        self.kernel.CloseHandle(self.handle)


def _worker(connection, cancellation, audio: str, size: int | None, repeats: int) -> None:
    # Native calls cannot be interrupted by Event; the parent measures that limit
    # before terminating this disposable worker. No partial transcript is published.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    def check() -> None:
        if cancellation.is_set():
            raise InterruptedError("Experimental transcription cancelled")

    try:
        profile = get_whisper_device_status("large-v3", "cpu")
        connection.send({"event": "loading", "profile": asdict(profile)})
        started = time.perf_counter()
        model, device = load_transcription_model("faster-whisper", "large-v3", "cpu")
        connection.send({
            "event": "loaded", "seconds": time.perf_counter() - started,
            "actual_device": str(model.model.device),
            "actual_compute_type": str(model.model.compute_type), "selected_device": device,
        })
        for index in range(repeats + 1):
            connection.send({"event": "run_started", "index": index})
            started = time.perf_counter()
            progress = []
            segments = []
            for segment in transcribe_segments(
                model, "faster-whisper", audio,
                experimental_batch_size=size, check_cancelled=check,
            ):
                segments.append(segment)
                progress.append({"elapsed_seconds": time.perf_counter() - started, "end": segment["end"]})
            elapsed = time.perf_counter() - started
            checkpoints = [0.0, *(item["elapsed_seconds"] for item in progress), elapsed]
            connection.send({
                "event": "run_completed", "index": index,
                "seconds": elapsed,
                "segments": segments, "progress": progress,
                "maximum_progress_gap_seconds": max(b - a for a, b in zip(checkpoints, checkpoints[1:])),
                "missing_word_timestamp_segments": sum(not segment["words"] for segment in segments),
            })
        connection.send({"event": "cancellation_started"})
        list(transcribe_segments(
            model, "faster-whisper", audio,
            experimental_batch_size=size, check_cancelled=check,
        ))
        connection.send({"event": "cancellation_finished", "completed_before_cancel": not cancellation.is_set()})
    except InterruptedError:
        connection.send({"event": "cancelled"})
    except Exception as exc:
        connection.send({
            "event": "error", "type": type(exc).__name__, "detail": str(exc),
            "diagnostic": traceback.format_exc(),
        })
    finally:
        connection.close()


def measure(audio: Path, size: int | None, repeats: int, timeout: float, output: Path) -> dict:
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    cancellation = context.Event()
    process = context.Process(target=_worker, args=(sender, cancellation, str(audio), size, repeats))
    result: dict[str, Any] = {"mode": mode_name(size), "runs": [], "errors": []}
    memory = None
    peaks: dict[str, int] = {}
    active = False
    pipe_closed = False
    cancel_due = requested = None
    started = time.perf_counter()
    process.start()
    sender.close()
    try:
        memory = WindowsMemory(process.pid)
        while True:
            while not pipe_closed:
                try:
                    if not receiver.poll():
                        break
                    event = receiver.recv()
                except (EOFError, BrokenPipeError):
                    pipe_closed = True
                    break
                kind = event["event"]
                if kind in ("loading", "loaded"):
                    result[kind] = event
                elif kind == "run_started":
                    peaks = {}
                    active = True
                    print(f"{mode_name(size)}: {'initial' if event['index'] == 0 else 'warm ' + str(event['index'])}", flush=True)
                elif kind == "run_completed":
                    active = False
                    event["sampled_peak_memory"] = dict(peaks)
                    result["runs"].append(event)
                    write_json(output / f"{mode_name(size)}-run-{event['index']}.json", event)
                    print(f"  {event['seconds']:.3f}s", flush=True)
                elif kind == "cancellation_started":
                    cancel_due = time.perf_counter() + 1.0
                elif kind in ("cancelled", "cancellation_finished"):
                    result["cancellation"] = {
                        "cooperative": kind == "cancelled",
                        "seconds": None if requested is None else time.perf_counter() - requested,
                        "completed_before_request": requested is None,
                        "threshold_passed": kind == "cancelled" and requested is not None
                        and time.perf_counter() - requested <= THRESHOLDS["maximum_cancellation_seconds"],
                    }
                elif kind == "error":
                    result["errors"].append(event)
            now = time.perf_counter()
            if not process.is_alive():
                if not pipe_closed:
                    continue
                break
            if active:
                sample = memory.sample()
                for key, value in sample.items():
                    peaks[key] = max(peaks.get(key, 0), value)
            if cancel_due is not None and requested is None and now >= cancel_due:
                cancellation.set()
                requested = now
            if requested is not None and now - requested >= THRESHOLDS["maximum_cancellation_seconds"]:
                process.terminate()
                process.join(5)
                result["cancellation"] = {
                    "cooperative": False, "forced_termination": True,
                    "seconds": time.perf_counter() - requested,
                    "threshold_passed": False,
                }
                break
            if now - started > timeout:
                raise TimeoutError(f"{mode_name(size)} exceeded {timeout}s; partial results retained. Choose a smaller clip or larger timeout.")
            time.sleep(0.1)
        process.join(5)
        result["exitcode"] = process.exitcode
        if process.exitcode != 0 and not result.get("cancellation", {}).get("forced_termination"):
            result["errors"].append({"detail": f"Worker exited unexpectedly with code {process.exitcode}."})
        if not result["runs"] and not result["errors"]:
            result["errors"].append({"detail": "Worker exited without a completed run; inspect exitcode."})
        warm = [run["seconds"] for run in result["runs"] if run["index"] > 0]
        result["warm_median_seconds"] = statistics.median(warm) if len(warm) == repeats else None
        result["warm_runs_complete"] = len(warm) == repeats
        return result
    except Exception as exc:
        result["errors"].append({"type": type(exc).__name__, "detail": str(exc)})
        write_json(output / f"{mode_name(size)}-failure.json", result)
        raise
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        if memory:
            memory.close()
        receiver.close()
        process.close()


def compare_reference(segments: list[dict], reference: list[dict], censor_words: set[str]) -> dict:
    """Agreement screen only: machine transcripts are not reviewed ground truth."""
    def token(word: str) -> str:
        return word.strip(".,!?;:'\" \t").lower()

    expected = [w for w in reference if token(w["word"]) in censor_words]
    detected = [w for s in segments for w in s["words"] if token(w["word"]) in censor_words]
    remaining = list(detected)
    errors = []
    uncovered = 0
    missed = 0
    boundaries = []
    for index, word in enumerate(expected):
        candidates = [w for w in remaining if token(w["word"]) == token(word["word"])
                      and abs(w["start"] - word["start"]) <= 1.0]
        if not candidates:
            missed += 1
            continue
        match = min(candidates, key=lambda w: abs(w["start"] - word["start"]))
        remaining.remove(match)
        errors.append(max(abs(match["start"] - word["start"]), abs(match["end"] - word["end"])))
        boundaries.append({
            "reference_index": index,
            "start_error_seconds": abs(match["start"] - word["start"]),
            "end_error_seconds": abs(match["end"] - word["end"]),
        })
        if max(0, match["start"] - 0.15) > word["start"] or match["end"] + 0.15 < word["end"]:
            uncovered += 1
    return {
        "reference_censor_words": len(expected), "missed": missed,
        "unmatched_detections": len(remaining), "uncovered_reference_intervals_at_150ms_padding": uncovered,
        "maximum_boundary_error_seconds": max(errors) if errors else None,
        "boundary_errors": boundaries,
        "recall": (len(expected) - missed) / len(expected) if expected else None,
        "status": "agreement_only_not_manually_verified_accuracy",
    }


def compare_to_standard(score: dict, baseline: dict) -> dict:
    standard = {item["reference_index"]: item for item in baseline["boundary_errors"]}
    additional = []
    for item in score["boundary_errors"]:
        previous = standard.get(item["reference_index"])
        if previous is not None:
            additional.extend(item[key] - previous[key] for key in ("start_error_seconds", "end_error_seconds"))
    maximum = max([0.0, *additional])
    return {
        "maximum_additional_boundary_error_seconds": maximum if additional else None,
        "timestamp_screen_passed": bool(score["reference_censor_words"])
        and score["missed"] == 0 and baseline["missed"] == 0
        and score["unmatched_detections"] <= baseline["unmatched_detections"]
        and score["uncovered_reference_intervals_at_150ms_padding"] == 0
        and maximum <= THRESHOLDS["maximum_additional_boundary_error_seconds"],
        "audible_review": "not performed; this screen cannot authorize adoption",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New experiment directory; must not exist")
    parser.add_argument("--reference", type=Path, help="Optional transcript for agreement, never trusted as reviewed truth")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--mode-timeout", type=float, default=1800.0)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This measurement runner requires Windows native memory counters.")
    if not (0 <= args.start < float("inf") and 0 < args.seconds < float("inf")
            and args.repeats >= 3 and 0 < args.mode_timeout < float("inf")):
        parser.error("Use finite start >= 0, seconds/timeout > 0, and at least three warm repetitions.")
    if importlib.metadata.version("faster-whisper") != "1.2.1":
        parser.error("The experiment requires the existing faster-whisper 1.2.1 pin; nothing is installed.")
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output == source.parent or source.is_relative_to(output):
        parser.error("Use a new experiment directory separate from source media.")
    ffmpeg, ffprobe = find_ffmpeg(), find_ffprobe()
    if not ffmpeg or not ffprobe:
        parser.error("Verified existing FFmpeg/FFprobe are required; use the approved setup flow first.")
    profile = get_whisper_device_status("large-v3", "cpu")
    if profile.selected != "cpu":
        parser.error("This initial runner measures CPU only. Remove conflicting device overrides; GPU qualification is separate.")
    output.mkdir(parents=True, exist_ok=False)
    policy = PolicyStore().load()
    censor_words = set(policy.censor_words) - set(policy.exclusions)
    summary: dict[str, Any] = {
        "thresholds": THRESHOLDS, "platform": platform.platform(),
        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
        "versions": {name: importlib.metadata.version(name) for name in
                     ("faster-whisper", "ctranslate2", "numpy", "av", "huggingface-hub")},
        "gpu_memory": "not applicable: CPU inference; no GPU measurements claimed",
        "profile": asdict(profile), "source": str(source), "start_seconds": args.start,
        "duration_seconds": args.seconds, "modes": [],
        "accuracy": "blocked pending manually reviewed word labels, six-category corpus and audible output review",
        "policy_censor_words": sorted(censor_words),
        "memory_sampling_interval_seconds": 0.1,
    }
    summary_path = output / "summary.json"
    with experiment_slot(), verified_source(source) as source_identity:
        original_digest = source_identity["digest"]
        summary["source_sha256"] = original_digest
        write_json(summary_path, summary)
        try:
            probe = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                 "stream=channels,channel_layout:format=duration", "-of", "json", str(source)],
                capture_output=True, text=True, check=True, timeout=30,
            )
            metadata = json.loads(probe.stdout)
            stream = metadata["streams"][0]
            if args.start + args.seconds > float(metadata["format"]["duration"]):
                raise ValueError("Excerpt exceeds media duration; choose a shorter range.")
            center = has_discrete_center_channel(stream["channels"], stream.get("channel_layout", ""))
            summary["audio_source"] = "front_center" if center else "full_mix"
            audio = output / "excerpt.wav"
            command = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-n",
                       "-ss", str(args.start), "-i", str(source), "-t", str(args.seconds),
                       "-map", "0:a:0", "-vn", "-sn", "-dn"]
            if center:
                command.extend(["-af", "pan=mono|c0=FC"])
            command.extend(["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])
            preparation = time.perf_counter()
            subprocess.run(command, capture_output=True, check=True, timeout=120)
            summary["excerpt_preparation_seconds"] = time.perf_counter() - preparation
            summary["excerpt_sha256"] = hashlib.sha256(audio.read_bytes()).hexdigest()
            reference = []
            if args.reference:
                payload = json.loads(args.reference.resolve(strict=True).read_text(encoding="utf-8"))
                reference = [
                    {**w, "start": w["start"] - args.start, "end": w["end"] - args.start}
                    for w in payload["words"]
                    if args.start <= w["start"] and w["end"] <= args.start + args.seconds
                ]
                summary["reference_status"] = "existing transcript; NOT manually reviewed ground truth"
            for size in MODES:
                measurement = measure(audio, size, args.repeats, args.mode_timeout, output)
                for run in measurement["runs"]:
                    if args.reference:
                        run["reference_agreement"] = compare_reference(run["segments"], reference, censor_words)
                        baseline_runs = summary["modes"][0]["runs"] if summary["modes"] else measurement["runs"]
                        baseline = next((item for item in baseline_runs if item["index"] == run["index"]), None)
                        if baseline is not None and "reference_agreement" in baseline:
                            run["comparison_to_standard"] = compare_to_standard(
                                run["reference_agreement"], baseline["reference_agreement"],
                            )
                summary["modes"].append(measurement)
                baseline = summary["modes"][0]["warm_median_seconds"]
                median = measurement["warm_median_seconds"]
                if baseline and median:
                    measurement["warm_speedup_percent"] = 100 * (baseline - median) / baseline
                    measurement["speed_threshold_passed"] = measurement["warm_speedup_percent"] >= 20
                write_json(summary_path, summary)
        finally:
            with source.open("rb") as handle:
                summary["source_unchanged"] = hash_stream(handle) == original_digest
            write_json(summary_path, summary)
            if not summary["source_unchanged"]:
                raise RuntimeError("Source identity changed during the experiment; results are invalid.")
    print(f"Results: {summary_path}", flush=True)
    if any(mode["errors"] or not mode["warm_runs_complete"] for mode in summary["modes"]):
        raise RuntimeError("One or more modes failed. See summary.json; no fallback or retry was performed.")


if __name__ == "__main__":
    main()
