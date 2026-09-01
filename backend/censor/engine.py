#!/usr/bin/env python3
"""Profanity Censoring Workflow - Whisper + FFmpeg"""

import os
import sys
import json
import math
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from threading import Event
from typing import Callable, List, Dict

from backend.policy import PolicyStore
from backend.runtime import (
    available_encoders,
    find_ffmpeg,
    find_ffprobe,
    get_calibrated_transcription_factor,
    get_whisper_cache_dir,
    get_whisper_device_status,
    record_transcription_timing,
    select_working_video_encoder,
    require_whisper_model,
)
from backend.runtime.transcription import (
    load_transcription_model,
    require_whisper_library,
    transcribe_segments,
)


def _profanity_dictionary():
    """Create an isolated vendor dictionary only when broad detection is requested."""
    from better_profanity import profanity

    # The package-level object is mutable. Sharing it lets dictionary review requests
    # replace the active processing policy while a job is running.
    return type(profanity)()


class TranscriptValidationError(RuntimeError):
    """Raised when a transcript cannot safely unlock downstream processing."""


def validate_transcript_data(
    transcript_data: object,
    *,
    whisper_library: str | None = None,
    whisper_model: str | None = None,
    require_front_center: bool = False,
) -> Dict:
    """Validate the persisted transcript contract used by detection and censoring."""
    if not isinstance(transcript_data, dict):
        raise TranscriptValidationError("Transcript must be a JSON object")
    if not isinstance(transcript_data.get("text"), str):
        raise TranscriptValidationError("Transcript text must be a string")

    words = transcript_data.get("words")
    if not isinstance(words, list):
        raise TranscriptValidationError("Transcript words must be a list")
    for index, item in enumerate(words):
        if not isinstance(item, dict) or not isinstance(item.get("word"), str):
            raise TranscriptValidationError(f"Transcript word {index} is invalid")
        start = item.get("start")
        end = item.get("end")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(float(start))
            or not math.isfinite(float(end))
            or start < 0
            or end < start
        ):
            raise TranscriptValidationError(
                f"Transcript word {index} has invalid timestamps"
            )

    audio_source = transcript_data.get("audio_source")
    if audio_source not in ("full_mix", "front_center"):
        raise TranscriptValidationError("Transcript audio source is invalid")
    if require_front_center and audio_source != "front_center":
        raise TranscriptValidationError(
            "Transcript must use the source's front-center audio channel"
        )
    if whisper_library and transcript_data.get("whisper_library") != whisper_library:
        raise TranscriptValidationError("Transcript uses a different Whisper library")
    if whisper_model and transcript_data.get("whisper_model") != whisper_model:
        raise TranscriptValidationError("Transcript uses a different Whisper model")
    return transcript_data


def write_transcript_atomic(
    transcript_path: Path,
    transcript_data: Dict,
    *,
    whisper_library: str,
    whisper_model: str,
    require_front_center: bool,
) -> Dict:
    """Atomically persist and verify a transcript before it can unlock transcoding."""
    validate = lambda value: validate_transcript_data(
        value,
        whisper_library=whisper_library,
        whisper_model=whisper_model,
        require_front_center=require_front_center,
    )
    validate(transcript_data)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=transcript_path.parent,
            prefix=f".{transcript_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(transcript_data, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        with temporary_path.open(encoding="utf-8") as source:
            validate(json.load(source))
        os.replace(temporary_path, transcript_path)
        temporary_path = None
        with transcript_path.open(encoding="utf-8") as source:
            return validate(json.load(source))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TranscriptValidationError(
            f"Transcript could not be saved and verified: {exc}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def probe_audio_stream(ffprobe_bin: str, input_file: str) -> tuple[int, str]:
    """Return the channel count and layout of the first audio stream."""
    try:
        result = subprocess.run(
            [ffprobe_bin, '-v', 'error', '-select_streams', 'a:0',
             '-show_entries', 'stream=channels,channel_layout', '-of', 'json',
             input_file],
            capture_output=True, text=True, timeout=5
        )
        streams = json.loads(result.stdout).get('streams', [])
        if not streams:
            return 0, ''
        return int(streams[0].get('channels', 0)), streams[0].get('channel_layout', '')
    except Exception:
        return 0, ''


def is_5_1_stream(channels: int, layout: str) -> bool:
    """Return whether audio metadata identifies a supported 5.1 layout."""
    return channels == 6 and layout in ('5.1', '5.1(side)')


def is_7_1_stream(channels: int, layout: str) -> bool:
    """Return whether audio metadata identifies a supported 7.1 layout."""
    return channels == 8 and layout in ('7.1', '7.1(wide)', '7.1(wide-side)')


def has_discrete_center_channel(channels: int, layout: str) -> bool:
    """Return whether audio has a supported discrete front-center channel."""
    return is_5_1_stream(channels, layout) or is_7_1_stream(channels, layout)


def transcript_cache_is_compatible(
    input_file: str,
    transcript_path: str,
    ffprobe_bin: str,
    whisper_library: str | None = None,
    whisper_model: str | None = None,
) -> bool:
    """Return whether a transcript exists and uses the right source channels."""
    if not os.path.exists(transcript_path):
        return False
    channels, layout = probe_audio_stream(ffprobe_bin, input_file)
    try:
        with open(transcript_path, 'r') as transcript_file:
            transcript_data = json.load(transcript_file)
        validate_transcript_data(
            transcript_data,
            whisper_library=whisper_library,
            whisper_model=whisper_model,
            require_front_center=has_discrete_center_channel(channels, layout),
        )
        return True
    except Exception:
        return False


def find_review_candidates(
    words_data: Dict,
    censor_words: set[str],
    exclude_words: set[str],
) -> List[Dict]:
    """Find vendor-list matches that a user has not yet classified as censor or ignore."""
    profanity = _profanity_dictionary()
    candidates = []
    for word_obj in words_data.get("words", []):
        word = str(word_obj.get("word", "")).strip(".,!?;:\"' \t")
        word_lower = word.lower()
        if not word or word_lower in censor_words or word_lower in exclude_words:
            continue
        if profanity.contains_profanity(word_lower):
            candidates.append(
                {
                    "word": word_lower,
                    "start": word_obj.get("start"),
                    "end": word_obj.get("end"),
                }
            )
    return candidates


def _parse_ffmpeg_time(value: str) -> float:
    """Convert FFmpeg's HH:MM:SS.microseconds progress value to seconds."""
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return 0.0


class ProcessingCancelled(RuntimeError):
    """Raised when an active media job is cancelled."""


def run_ffmpeg_with_progress(
    command: list[str],
    duration: float | None,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    cancellation: Event | None = None,
) -> subprocess.CompletedProcess:
    """Run FFmpeg and render its machine-readable progress stream."""
    progress_command = command[:1] + [
        "-hide_banner", "-loglevel", "error", "-nostats",
        "-progress", "pipe:1",
    ] + command[1:]
    started = time.perf_counter()
    last_percent = -1
    rendered = False

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as error_file:
        process = subprocess.Popen(
            progress_command,
            stdout=subprocess.PIPE,
            stderr=error_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        progress_values: dict[str, str] = {}
        if process.stdout is not None:
            for line in process.stdout:
                if cancellation is not None and cancellation.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise ProcessingCancelled("Media processing was cancelled")
                key, separator, value = line.strip().partition("=")
                if not separator:
                    continue
                progress_values[key] = value
                if key != "progress":
                    continue

                encoded_seconds = _parse_ffmpeg_time(progress_values.get("out_time", ""))
                if duration and duration > 0:
                    percent = min(100, int(encoded_seconds / duration * 100))
                else:
                    percent = 100 if value == "end" else 0
                if value == "end":
                    percent = 100
                if percent == last_percent and value != "end":
                    continue

                speed_text = progress_values.get("speed", "N/A").strip() or "N/A"
                try:
                    speed = float(speed_text.rstrip("x"))
                except ValueError:
                    speed = 0.0
                remaining = max(0.0, (duration or 0.0) - encoded_seconds)
                eta = ProfanityCensor._format_seconds(remaining / speed) if speed > 0 else "--:--"
                elapsed = ProfanityCensor._format_seconds(time.perf_counter() - started)
                filled = int(percent * 24 / 100)
                bar = "#" * filled + "-" * (24 - filled)
                status = (
                    f"\r[FFmpeg] [{bar}] {percent:3d}% | fps {progress_values.get('fps', 'N/A')} | "
                    f"speed {speed_text} | elapsed {elapsed} | eta {eta}"
                )
                sys.stdout.write(status)
                sys.stdout.flush()
                if progress_callback is not None:
                    progress_callback(
                        {
                            "percent": float(percent),
                            "eta_seconds": remaining / speed if speed > 0 else None,
                            "fps": float(progress_values["fps"])
                            if progress_values.get("fps", "").replace(".", "", 1).isdigit()
                            else None,
                            "message": f"FFmpeg speed {speed_text}",
                        }
                    )
                rendered = True
                last_percent = percent

        returncode = process.wait()
        error_file.seek(0)
        stderr = error_file.read()

    if rendered:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return subprocess.CompletedProcess(progress_command, returncode, "", stderr)



class ProfanityCensor:
    def __init__(self, input_file: str, output_file: str, model_name: str = "large-v3",
                 transcripts_dir: str = None, whisper_model=None,
                 whisper_library: str = "faster-whisper",
                 whisper_device: str = "auto",
                 censor_method: str = "mute", padding_before_ms: int = 150,
                 padding_after_ms: int = 150, surround_output: str = "preserve_5_1",
                 video_mode: str = "h264",
                 progress_callback: Callable[[dict[str, object]], None] | None = None,
                 cancellation: Event | None = None, ffmpeg_bin: str | None = None,
                 ffprobe_bin: str | None = None, whisper_cache_dir: Path | None = None,
                 policy_store: PolicyStore | None = None):
        self.input_file = input_file
        self.output_file = output_file
        self.model_name = require_whisper_model(model_name)
        self.whisper_library = require_whisper_library(whisper_library)
        self.whisper_device = whisper_device
        self.transcripts_dir = transcripts_dir
        self.whisper_cache_dir = (whisper_cache_dir or get_whisper_cache_dir()).resolve()
        self._shared_model = whisper_model  # pre-loaded (WhisperModel, device) tuple or None
        self.censor_method = censor_method if censor_method in ("mute", "karaoke") else "mute"
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000
               for value in (padding_before_ms, padding_after_ms)):
            raise ValueError("Censor padding must be an integer from 0 through 10000 milliseconds")
        if surround_output not in ("preserve_5_1", "downmix_stereo"):
            raise ValueError("Unsupported surround output mode")
        if video_mode not in ("h264", "preserve_source"):
            raise ValueError("Unsupported video output mode")
        self.padding_before_ms = padding_before_ms
        self.padding_after_ms = padding_after_ms
        self.surround_output = surround_output
        self.video_mode = video_mode
        self.progress_callback = progress_callback
        self.cancellation = cancellation or Event()
        self.ffmpeg_bin = ffmpeg_bin or find_ffmpeg()
        self.ffprobe_bin = ffprobe_bin or find_ffprobe()
        if not self.ffmpeg_bin or not self.ffprobe_bin:
            raise RuntimeError(
                "FFmpeg and FFprobe must be available on PATH or configured with "
                "CENSOR_FFMPEG and CENSOR_FFPROBE."
            )
        self.encoders = available_encoders(self.ffmpeg_bin)
        self.video_encoder = select_working_video_encoder(
            self.ffmpeg_bin,
            self.encoders,
            os.environ.get("CENSOR_VIDEO_ENCODER"),
        )
        self.policy_store = policy_store or PolicyStore()
        policy = self.policy_store.load()
        self.censor_words_file = policy.censor_defaults_path
        self.censor_words = set(policy.censor_words)
        self.exclusions_file = policy.exclusions_defaults_path
        self.exclude_words = set(policy.exclusions)
        self.policy_file = policy.overrides_path
        self.review_candidates: list[dict] = []
        self.used_cached_transcript: bool = False
        self.profane_count: int = 0
        self.last_error: str | None = None
        print(
            f"[*] Loaded {len(self.censor_words)} profanity censor word(s) "
            f"from {self.policy_file}"
        )
        print(f"[*] Loaded {len(self.exclude_words)} profanity exclusion(s)")

    def _check_cancelled(self) -> None:
        cancellation = getattr(self, "cancellation", None)
        if cancellation is not None and cancellation.is_set():
            raise ProcessingCancelled("Media processing was cancelled")

    def _emit_progress(
        self,
        stage: str,
        percent: float | None = None,
        eta_seconds: float | None = None,
        fps: float | None = None,
        message: str | None = None,
    ) -> None:
        progress_callback = getattr(self, "progress_callback", None)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "progress",
                    "stage": stage,
                    "percent": percent,
                    "eta_seconds": eta_seconds,
                    "fps": fps,
                    "message": message,
                }
            )

    def _emit_detection(self, word: str, start: float, end: float) -> None:
        progress_callback = getattr(self, "progress_callback", None)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "detection",
                    "stage": "transcribing",
                    "word": word,
                    "start": start,
                    "end": end,
                }
            )

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        whole = max(0, int(round(seconds)))
        hours, remainder = divmod(whole, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def get_media_duration_seconds(self) -> float | None:
        try:
            result = subprocess.run(
                [
                    self.ffprobe_bin,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    self.input_file,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return None
            duration = float(result.stdout.strip())
            return duration if duration > 0 else None
        except Exception:
            return None

    def estimate_processing_seconds(self, has_cached_transcript: bool) -> dict[str, float | str]:
        duration = self.get_media_duration_seconds()
        if duration is None:
            return {"total": 0.0, "transcribe": 0.0, "detect": 0.0, "censor": 0.0, "source": ""}

        fallback_factor = 6.5
        calibrated_factor = get_calibrated_transcription_factor(self.model_name)
        factor = calibrated_factor or fallback_factor
        transcribe = 0.0 if has_cached_transcript else duration * factor
        source = "cached transcript" if has_cached_transcript else (
            f"local calibration ({factor:.2f}x media duration)"
            if calibrated_factor else f"conservative fallback ({fallback_factor:.1f}x media duration)"
        )

        detect = max(5.0, duration * 0.03)
        if self.is_audio_only():
            censor = max(8.0, duration * 0.35)
        else:
            video_codec = self.get_video_codec()
            if video_codec == 'h264':
                censor = max(10.0, duration * 0.28)
            elif self.video_encoder == 'libx264':
                censor = max(12.0, duration * 1.2)
            else:
                censor = max(10.0, duration * 0.6)

        total = transcribe + detect + censor
        return {"total": total, "transcribe": transcribe, "detect": detect, "censor": censor, "source": source}

    def _preferred_whisper_device(self) -> str:
        return get_whisper_device_status(self.model_name).selected

    def _load_whisper_model(self):
        status = get_whisper_device_status(self.model_name, self.whisper_device)
        print(f"[*] Whisper profile: {status.selected} ({status.compute_type}); {status.detail}")
        return load_transcription_model(
            self.whisper_library,
            self.model_name,
            self.whisper_device,
            cache_dir=self.whisper_cache_dir,
        )

    def get_transcript_path(self) -> str:
        """Get path for transcript file."""
        if not self.transcripts_dir:
            return None
        file_base = os.path.splitext(os.path.basename(self.input_file))[0]
        return os.path.join(self.transcripts_dir, f"{file_base}-transcript.json")

    def is_audio_only(self) -> bool:
        """Check if input file is audio-only."""
        try:
            result = subprocess.run(
                [self.ffprobe_bin, '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_type', '-of', 'csv=p=0',
                 self.input_file],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() == ''
        except:
            return False

    def get_video_codec(self) -> str:
        """Return the video codec name, e.g. 'h264', 'hevc'."""
        try:
            result = subprocess.run(
                [self.ffprobe_bin, '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_name', '-of', 'csv=p=0',
                 self.input_file],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip().lower()
        except:
            return ''

    def get_audio_stream_info(self) -> tuple[int, str]:
        """Return the channel count and layout of the first audio stream."""
        return probe_audio_stream(self.ffprobe_bin, self.input_file)

    def get_audio_channels(self) -> int:
        """Return the channel count of the first audio stream (0 on failure)."""
        return self.get_audio_stream_info()[0]

    def is_5_1_audio(self) -> bool:
        """Return whether the first audio stream has a recognized 5.1 layout."""
        channels, layout = self.get_audio_stream_info()
        return is_5_1_stream(channels, layout)

    def has_discrete_center_audio(self) -> bool:
        """Return whether the first audio stream has a supported center channel."""
        channels, layout = self.get_audio_stream_info()
        return has_discrete_center_channel(channels, layout)

    def get_output_file(self, base_name: str = None) -> str:
        """Get output filename with appropriate extension."""
        if base_name is None:
            base_name = os.path.splitext(os.path.basename(self.input_file))[0]

        if self.is_audio_only():
            return f"{base_name}-censored.mp3"
        else:
            return f"{base_name}-censored.mkv"

    def extract_center_channel(self) -> str:
        """Extract the front-center channel to a mono WAV for transcription."""
        print("[*] Extracting surround front-center channel for transcription...")

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            audio_file = tmp.name

        try:
            cmd = [self.ffmpeg_bin, '-v', 'quiet', '-i', self.input_file,
                   '-map', '0:a:0', '-af', 'pan=mono|c0=FC', '-ar', '16000',
                   '-c:a', 'pcm_s16le', '-y', audio_file]
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"[+] Front-center channel extracted: {audio_file}")
            return audio_file
        except subprocess.CalledProcessError as e:
            if os.path.exists(audio_file):
                os.unlink(audio_file)
            print(f"[-] Failed to extract front-center channel: {e}")
            raise

    def transcribe_with_timestamps(self, force: bool = False) -> Dict:
        """Transcribe audio using Whisper or load from cached transcript."""
        transcript_path = self.get_transcript_path()
        if not transcript_path:
            raise TranscriptValidationError(
                "A transcripts directory is required before media can be processed"
            )
        transcript_file = Path(transcript_path)
        require_front_center = self.has_discrete_center_audio()

        if transcript_file.exists() and not force:
            print(f"[*] Loading cached transcript...")
            try:
                with transcript_file.open(encoding="utf-8") as f:
                    transcript_data = json.load(f)
                validate_transcript_data(
                    transcript_data,
                    whisper_library=self.whisper_library,
                    whisper_model=self.model_name,
                    require_front_center=require_front_center,
                )
                self.used_cached_transcript = True
                return transcript_data
            except Exception as e:
                print(f"[!] Failed to load cached transcript, re-transcribing: {e}")

        print(f"[*] Transcribing with {self.whisper_library} ({self.model_name})...")

        temporary_audio = None
        try:
            if self._shared_model is not None:
                model = self._shared_model[0]
            else:
                model = self._load_whisper_model()[0]

            duration = self.get_media_duration_seconds() or 0.0
            transcription_input = self.input_file
            if require_front_center:
                temporary_audio = self.extract_center_channel()
                transcription_input = temporary_audio
            # hallucination_silence_threshold prevents drift from hallucinated content in silent sections
            segments_gen = transcribe_segments(model, self.whisper_library, transcription_input)

            words_with_timestamps = []
            full_text_parts = []
            tx_started = time.perf_counter()
            last_percent = -1
            initial_status = "[Whisper] [------------------------]   0% | speed N/A | elapsed 00:00 | eta --:--"
            sys.stdout.write(f"\r{initial_status:<110}")
            sys.stdout.flush()
            self._emit_progress("transcribing", 0.0, message="Transcription started")

            for segment in segments_gen:
                self._check_cancelled()
                full_text_parts.append(segment["text"])
                if segment["words"]:
                    for w in segment["words"]:
                        words_with_timestamps.append({
                            'word': str(w["word"]).strip('.,!?;:'),
                            'start': w["start"],
                            'end': w["end"],
                        })
                else:
                    parts = segment["text"].split()
                    num_parts = len(parts)
                    seg_dur = segment["end"] - segment["start"]
                    if num_parts:
                        for i, word in enumerate(parts):
                            words_with_timestamps.append({
                                'word': word.strip('.,!?;:'),
                                'start': segment["start"] + (i / num_parts) * seg_dur,
                                'end': segment["start"] + ((i + 1) / num_parts) * seg_dur,
                            })

                if duration > 0:
                    progress = min(100, int(segment["end"] / duration * 100))
                    if progress != last_percent:
                        elapsed = time.perf_counter() - tx_started
                        rate = segment["end"] / elapsed if elapsed > 0 and segment["end"] > 0 else 0
                        remaining = (duration - segment["end"]) / rate if rate > 0 else 0
                        filled = int(progress * 24 / 100)
                        bar = "#" * filled + "-" * (24 - filled)
                        speed = f"{rate:.2f}x" if rate > 0 else "N/A"
                        eta = self._format_seconds(remaining) if rate > 0 else "--:--"
                        status = (
                            f"[Whisper] [{bar}] {progress:3d}% | speed {speed} | "
                            f"elapsed {self._format_seconds(elapsed)} | eta {eta}"
                        )
                        sys.stdout.write(f"\r{status:<110}")
                        sys.stdout.flush()
                        self._emit_progress(
                            "transcribing",
                            float(progress),
                            remaining if rate > 0 else None,
                            message=f"Whisper speed {speed}",
                        )
                        last_percent = progress

            elapsed = time.perf_counter() - tx_started
            completed_status = (
                f"[Whisper] [########################] 100% | "
                f"elapsed {self._format_seconds(elapsed)} | eta 00:00"
            )
            sys.stdout.write(f"\r{completed_status:<110}\n")
            sys.stdout.flush()
            self._emit_progress("transcribing", 100.0, 0.0, message="Transcription completed")
            print(f"[+] Transcription complete: {len(words_with_timestamps)} words")
            record_transcription_timing(duration, elapsed, self.model_name)

            transcript_data = {
                'text': "".join(full_text_parts),
                'words': words_with_timestamps,
                'audio_source': 'front_center' if temporary_audio else 'full_mix',
                'whisper_library': self.whisper_library,
                'whisper_model': self.model_name,
            }

            persisted_transcript = write_transcript_atomic(
                transcript_file,
                transcript_data,
                whisper_library=self.whisper_library,
                whisper_model=self.model_name,
                require_front_center=require_front_center,
            )
            print(f"[+] Transcript saved and verified: {transcript_path}")
            return persisted_transcript
        except Exception as e:
            print(f"[-] Transcription failed: {e}")
            raise
        finally:
            if temporary_audio and os.path.exists(temporary_audio):
                os.unlink(temporary_audio)

    def detect_profanity(self, words_data: Dict, include_undiscovered: bool = False) -> List[Dict]:
        """Detect configured words, optionally including undiscovered vendor-list matches."""
        print(f"[*] Detecting profanity...")

        profane_words = []
        vendor_dictionary = _profanity_dictionary() if include_undiscovered else None

        for word_obj in words_data['words']:
            word = word_obj['word'].strip('.,!?;:\'" \t')
            word_lower = word.lower()

            if word_lower in self.exclude_words:
                continue

            # The curated set is the processing source of truth; the vendor list is
            # consulted only for the explicit include-undiscovered workflow.
            configured_match = word_lower in self.censor_words
            vendor_match = (
                vendor_dictionary is not None
                and vendor_dictionary.contains_profanity(word_lower)
            )
            if configured_match or vendor_match:
                detection = {
                    'word': word,
                    'start': word_obj['start'],
                    'end': word_obj['end'],
                }
                profane_words.append(detection)
                self._emit_detection(word, detection['start'], detection['end'])

        self.profane_count = len(profane_words)
        print(f"[+] Found {len(profane_words)} profane word(s)")
        for pw in profane_words:
            print(f"    - '{pw['word']}' at {pw['start']:.2f}s")

        return profane_words

    def find_review_candidates(self, words_data: Dict) -> List[Dict]:
        """Find broad-vocabulary matches not covered by the current policy."""
        return find_review_candidates(words_data, self.censor_words, self.exclude_words)

    def report_potential_profanity(self, words_data: Dict) -> List[Dict]:
        """Print broad-vocabulary matches for policy review without censoring media."""
        candidates = self.find_review_candidates(words_data)
        grouped_candidates = defaultdict(list)
        for candidate in candidates:
            grouped_candidates[candidate["word"]].append(candidate["start"])

        print("[*] Potential profanity review:")
        if not grouped_candidates:
            print("    No additional candidates found outside the current policy.")
            return candidates

        for word, timestamps in sorted(grouped_candidates.items()):
            formatted_timestamps = ", ".join(f"{timestamp:.2f}s" for timestamp in timestamps[:5])
            remaining = len(timestamps) - 5
            suffix = f" (+{remaining} more)" if remaining > 0 else ""
            print(f"    - {word}: {len(timestamps)} occurrence(s) at {formatted_timestamps}{suffix}")
        print("[*] Add a word to profanity_censor_words.txt to censor it, or profanity_exclusions.txt to ignore it.")
        return candidates

    def _build_interval_expr(self, profane_segments: List[Dict]) -> str:
        """Build the FFmpeg timeline expression for all censor intervals."""
        parts = []
        padding_before = getattr(self, "padding_before_ms", 150) / 1000
        padding_after = getattr(self, "padding_after_ms", 150) / 1000
        for segment in profane_segments:
            start = max(0, segment['start'] - padding_before)
            end = segment['end'] + padding_after
            parts.append(f"between(t,{start},{end})")
        return "+".join(parts)

    def generate_muting_filter(self, profane_segments: List[Dict]) -> str:
        """Generate FFmpeg audio muting filter (-af simple filter)."""
        if not profane_segments:
            return None

        print(f"[*] Generating muting filter...")
        enable_filter = self._build_interval_expr(profane_segments)
        filter_string = f"volume=0:enable='{enable_filter}'"

        print(f"[+] Filter generated ({len(profane_segments)} segments)")
        return filter_string

    def generate_karaoke_filter_complex(self, profane_segments: List[Dict]) -> str | None:
        """Generate a filter_complex that removes centre audio only during censor intervals.

        Stereo sources use channel subtraction to cancel centre-panned audio. For 5.1/7.1,
        the discrete front-center channel is dropped while every other channel is retained.
        Outside the censor intervals the original stream is passed through unchanged.
        """
        if not profane_segments:
            return None

        channels, layout = self.get_audio_stream_info()
        if channels == 2:
            centre_filter = "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0"
        elif has_discrete_center_channel(channels, layout):
            channel_maps = [f"c{index}={'0*' if index == 2 else ''}c{index}" for index in range(channels)]
            centre_filter = f"pan={layout}|{'|'.join(channel_maps)}"
        else:
            print(
                f"[!] Karaoke mode requires stereo, 5.1, or 7.1 audio (detected {channels} channel(s)); "
                "falling back to mute."
            )
            return None

        print("[*] Generating karaoke filter complex...")
        intervals = self._build_interval_expr(profane_segments)
        # During intervals: mute the original and pass the centre-cancelled track.
        # Outside intervals: mute the karaoke track and pass the original.
        graph = (
            "[0:a]asplit=2[_aorig][_afork];"
            f"[_afork]{centre_filter}[_akara];"
            f"[_aorig]volume=0:enable='{intervals}'[_aorig_g];"
            f"[_akara]volume=0:enable='not({intervals})'[_akara_g];"
            "[_aorig_g][_akara_g]amix=inputs=2:normalize=0[outa]"
        )
        print(f"[+] Karaoke filter generated ({len(profane_segments)} segment(s))")
        return graph

    def censor_video(self, profane_segments: List[Dict]) -> bool:
        """Apply audio muting to video using ffmpeg."""
        os.makedirs(os.path.dirname(os.path.abspath(self.output_file)), exist_ok=True)
        source_has_center_channel = self.has_discrete_center_audio()
        audio_only = self.is_audio_only()
        video_mode = getattr(self, "video_mode", "h264")
        surround_output = getattr(self, "surround_output", "preserve_5_1")
        source_video_codec = "" if audio_only else self.get_video_codec()
        can_copy_clean = (
            not audio_only
            and (not source_has_center_channel or surround_output == "preserve_5_1")
            and (video_mode == "preserve_source" or source_video_codec == "h264")
        )
        if not profane_segments and can_copy_clean:
            print("[*] No profanity detected. Copying file...")
            try:
                result = run_ffmpeg_with_progress(
                    [self.ffmpeg_bin, '-i', self.input_file,
                     '-c', 'copy', '-y', self.output_file],
                    self.get_media_duration_seconds(),
                    lambda progress: self._emit_progress("censoring", **progress),
                    getattr(self, "cancellation", None),
                )
                if result.returncode != 0:
                    error_lines = [line for line in result.stderr.splitlines() if line.strip()]
                    error_detail = error_lines[-1] if error_lines else "unknown FFmpeg error"
                    self.last_error = f"FFmpeg failed to copy the file: {error_detail}"
                    print(f"[-] Failed to copy file: {error_detail}")
                    return False
                print(f"[+] File copied: {self.output_file}")
                return True
            except OSError as e:
                self.last_error = f"Failed to copy file: {e}"
                print(f"[-] Failed to copy file: {e}")
                return False

        if profane_segments:
            method = "surround center-channel ducking" if source_has_center_channel else self.censor_method
            print(f"[*] Applying censoring (method: {method})...")
        elif source_has_center_channel and surround_output == "downmix_stereo":
            print("[*] No profanity detected. Downmixing surround audio to stereo...")
        else:
            print("[*] No profanity detected. Applying requested output settings...")

        # Supported surround layouts always use their center channel; stereo karaoke remains opt-in.
        use_filter_complex = False
        filter_complex = None
        if profane_segments and (source_has_center_channel or self.censor_method == "karaoke"):
            filter_complex = self.generate_karaoke_filter_complex(profane_segments)
            use_filter_complex = filter_complex is not None

        if not use_filter_complex:
            audio_filter = self.generate_muting_filter(profane_segments) if profane_segments else "anull"
        else:
            audio_filter = None

        try:
            video_codec = source_video_codec

            def _build_cmd(video_enc: str) -> list:
                base = [self.ffmpeg_bin, '-i', self.input_file]
                if use_filter_complex:
                    base += ['-filter_complex', filter_complex]
                    if not audio_only:
                        # preserve video, processed audio, and any subtitle streams
                        base += ['-map', '0:v', '-map', '[outa]', '-map', '0:s?']
                    else:
                        base += ['-map', '[outa]']
                else:
                    base += ['-af', audio_filter]

                if audio_only:
                    base += ['-c:a', 'libmp3lame', '-q:a', '4']
                else:
                    base += ['-c:v', video_enc, '-c:a', 'aac']
                if (
                    source_has_center_channel
                    and getattr(self, "surround_output", "preserve_5_1") == "downmix_stereo"
                ):
                    base += ['-ac', '2']
                base += ['-y', self.output_file]
                return base

            if audio_only:
                if use_filter_complex:
                    print("[*] Karaoke mode (audio-only)")
                cmd = _build_cmd('')
            else:
                if video_mode == 'preserve_source':
                    print("[*] Preserving source video stream...")
                    cmd = _build_cmd('copy')
                elif video_codec == 'h264':
                    print("[*] Video is already H.264, copying stream...")
                    cmd = _build_cmd('copy')
                else:
                    print(f"[*] Video encoder: {self.video_encoder}")
                    cmd = _build_cmd(self.video_encoder)

            label = "Center-channel" if source_has_center_channel and use_filter_complex else (
                "Karaoke" if use_filter_complex else "Muting"
            )
            preview = filter_complex[:80] if use_filter_complex else audio_filter[:80]
            print(f"[*] {label} filter: {preview}...")

            duration = self.get_media_duration_seconds()
            result = run_ffmpeg_with_progress(
                cmd,
                duration,
                lambda progress: self._emit_progress("censoring", **progress),
                getattr(self, "cancellation", None),
            )

            # A detected hardware encoder may still fail at runtime (for example, no GPU device).
            if (
                result.returncode != 0
                and not audio_only
                and getattr(self, "video_mode", "h264") == 'h264'
                and video_codec != 'h264'
                and self.video_encoder != 'libx264'
                and 'libx264' in self.encoders
            ):
                error_lines = [line for line in result.stderr.splitlines() if line.strip()]
                error_detail = error_lines[-1] if error_lines else "unknown FFmpeg error"
                print(
                    f"[!] Encoder {self.video_encoder} failed ({error_detail}); "
                    "using software fallback..."
                )
                cmd = _build_cmd('libx264')
                result = run_ffmpeg_with_progress(
                    cmd,
                    duration,
                    lambda progress: self._emit_progress("censoring", **progress),
                    getattr(self, "cancellation", None),
                )

            if result.returncode == 0:
                print(f"[+] Video censored: {self.output_file}")
                return True
            else:
                error_lines = [line for line in result.stderr.splitlines() if line.strip()]
                error_detail = error_lines[-1] if error_lines else result.stderr[:500]
                self.last_error = f"FFmpeg failed: {error_detail}"
                print(f"[-] FFmpeg failed: {result.stderr[:200]}")
                return False

        except Exception as e:
            self.last_error = f"Error during censoring: {e}"
            print(f"[-] Error during censoring: {e}")
            return False

    def process(
        self,
        report_only: bool = False,
        include_undiscovered: bool = False,
        force_transcribe: bool = False,
    ) -> bool:
        """Execute the complete censoring pipeline."""
        started = time.perf_counter()
        transcript_path = self.get_transcript_path()
        has_cached_transcript = bool(transcript_path and os.path.exists(transcript_path))
        estimate = self.estimate_processing_seconds(has_cached_transcript)

        if estimate["total"] > 0:
            print("[*] Planned stages:")
            print(
                "    1) Transcribe / load transcript ~"
                f" {self._format_seconds(estimate['transcribe'])}"
            )
            print(f"       Estimate source: {estimate['source']}")
            print(
                "    2) Detect profanity          ~"
                f" {self._format_seconds(estimate['detect'])}"
            )
            if not report_only:
                print(
                    "    3) Apply censoring           ~"
                    f" {self._format_seconds(estimate['censor'])}"
                )
            if include_undiscovered and not report_only:
                print("    Undiscovered vendor-list matches will also be censored unless excluded.")
            shown_total = estimate['transcribe'] + estimate['detect'] if report_only else estimate['total']
            print(f"[*] Estimated total runtime: ~{self._format_seconds(shown_total)}")

        try:
            self._check_cancelled()
            stage_started = time.perf_counter()
            # Transcribe the original file directly (gets accurate timestamps)
            if force_transcribe:
                self.transcribe_with_timestamps(force=True)
            else:
                self.transcribe_with_timestamps()
            if not transcript_path:
                raise TranscriptValidationError(
                    "A persisted transcript is required before processing can continue"
                )
            # Re-open the artifact rather than trusting an in-memory result. This is
            # the final gate shared by report-only and censor/transcode jobs.
            with Path(transcript_path).open(encoding="utf-8") as transcript_file:
                words_data = validate_transcript_data(
                    json.load(transcript_file),
                    whisper_library=self.whisper_library,
                    whisper_model=self.model_name,
                    require_front_center=self.has_discrete_center_audio(),
                )
            self._check_cancelled()
            print(
                f"[+] Stage 1 complete in {self._format_seconds(time.perf_counter() - stage_started)}"
            )

            stage_started = time.perf_counter()
            # Detect profanity
            self.review_candidates = self.find_review_candidates(words_data)
            policy_store = getattr(self, "policy_store", None)
            if policy_store is not None:
                policy_store.add_discovered({
                    candidate["word"] for candidate in self.review_candidates
                })
            if include_undiscovered:
                self.report_potential_profanity(words_data)
            profane_segments = self.detect_profanity(words_data, include_undiscovered)
            self._check_cancelled()
            print(
                f"[+] Stage 2 complete in {self._format_seconds(time.perf_counter() - stage_started)}"
            )

            if report_only:
                self.report_potential_profanity(words_data)
                print("[*] Report-only complete. No output file was created and source media was not moved.")
                print(f"[*] Total elapsed: {self._format_seconds(time.perf_counter() - started)}")
                return True

            stage_started = time.perf_counter()
            # Censor video
            self._emit_progress("censoring", 0.0, message="Censoring started")
            success = self.censor_video(profane_segments)
            print(
                f"[+] Stage 3 complete in {self._format_seconds(time.perf_counter() - stage_started)}"
            )
            print(f"[*] Total elapsed: {self._format_seconds(time.perf_counter() - started)}")

            return success

        except Exception as e:
            self.last_error = str(e)
            print(f"[-] Processing failed: {e}")
            print(f"[*] Total elapsed before failure: {self._format_seconds(time.perf_counter() - started)}")
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe and censor one media file")
    parser.add_argument("input_file")
    parser.add_argument("output_file")
    parser.add_argument("model", nargs="?", default="large", choices=["large"])
    parser.add_argument("transcripts_dir", nargs="?")
    parser.add_argument("--report-only", action="store_true", help="List policy review candidates without changing media")
    parser.add_argument(
        "--include-undiscovered",
        action="store_true",
        help="Also censor vendor-list matches that are not included or excluded",
    )
    parser.add_argument(
        "--censor-method",
        default="mute",
        choices=["mute", "karaoke"],
        help="mute: silence profane intervals (default); karaoke: cancel centre-panned audio",
    )
    parser.add_argument("--padding-before-ms", type=int, default=150)
    parser.add_argument("--padding-after-ms", type=int, default=150)
    parser.add_argument(
        "--surround-output",
        choices=["preserve_5_1", "downmix_stereo"],
        default="preserve_5_1",
    )
    parser.add_argument(
        "--video-mode",
        choices=["h264", "preserve_source"],
        default="h264",
    )
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file
    required_model = args.model
    transcripts_dir = args.transcripts_dir

    if not os.path.exists(input_file):
        print(f"[-] Input file not found: {input_file}")
        sys.exit(1)

    print("=" * 70)
    print("  Profanity Censoring Workflow")
    print("=" * 70)
    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    print(f"Model:  {required_model}")
    if transcripts_dir:
        print(f"Transcripts: {transcripts_dir}")
    if args.report_only and args.include_undiscovered:
        parser.error("--report-only and --include-undiscovered cannot be used together")
    if args.report_only:
        print("Mode:   report-only (no media output or archival)")
    elif args.include_undiscovered:
        print("Mode:   censoring configured and undiscovered vendor-list words")
    print()

    censor = ProfanityCensor(
        input_file,
        output_file,
        required_model,
        transcripts_dir,
        censor_method=args.censor_method,
        padding_before_ms=args.padding_before_ms,
        padding_after_ms=args.padding_after_ms,
        surround_output=args.surround_output,
        video_mode=args.video_mode,
    )
    success = censor.process(
        report_only=args.report_only,
        include_undiscovered=args.include_undiscovered,
    )

    print()
    if success:
        print("[OK] Processing complete!")
        sys.exit(0)
    else:
        print("[FAILED] Processing failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
