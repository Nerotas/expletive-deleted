#!/usr/bin/env python3
"""Profanity Censoring Workflow - Whisper + FFmpeg"""

import os
import sys
import json
import shutil
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
    resolve_media_tools,
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

from .detection import _profanity_dictionary, find_review_candidates
from .media import probe_audio_stream, is_5_1_stream, is_7_1_stream, has_discrete_center_channel
from .transcripts import (
    TranscriptValidationError,
    validate_transcript_data,
    write_transcript_atomic,
    transcript_cache_is_compatible,
)
from .ffmpeg import ProcessingCancelled, run_ffmpeg_with_progress, format_seconds


class ProfanityCensor:
    def __init__(self, input_file: str, output_file: str, model_name: str = "large-v3",
                 transcripts_dir: str = None, whisper_model=None,
                 whisper_library: str = "faster-whisper",
                 whisper_device: str = "auto",
                 censor_method: str = "mute", padding_before_ms: int = 150,
                 padding_after_ms: int = 150, surround_output: str = "preserve_5_1",
                 video_mode: str = "preserve_source",
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
        self.ffmpeg_bin, self.ffprobe_bin = resolve_media_tools(ffmpeg_bin, ffprobe_bin)
        if not self.ffmpeg_bin or not self.ffprobe_bin:
            raise RuntimeError(
                "FFmpeg and FFprobe must be available on PATH or configured with "
                "CENSOR_FFMPEG and CENSOR_FFPROBE."
            )
        self.encoders: set[str] = set()
        self.video_encoder: str | None = None
        self.policy_store = policy_store or PolicyStore()
        policy = self.policy_store.load()
        self.censor_words_file = policy.censor_defaults_path
        self.censor_words = set(policy.censor_words)
        self.exclusions_file = policy.exclusions_defaults_path
        self.exclude_words = set(policy.exclusions)
        self.dictionary_directory = policy.dictionary_path
        self.review_candidates: list[dict] = []
        self.used_cached_transcript: bool = False
        self.profane_count: int = 0
        self.last_error: str | None = None
        print(
            f"[*] Loaded {len(self.censor_words)} profanity censor word(s) "
            f"from {self.dictionary_directory}"
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
        return format_seconds(seconds)

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

    def validate_transcription_audio(self, input_file: str | None = None) -> None:
        """Reject media whose selected audio stream cannot produce samples for Whisper."""
        source = input_file or self.input_file
        result = subprocess.run(
            [
                self.ffprobe_bin,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,channels,sample_rate,duration",
                "-of", "json",
                source,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise TranscriptValidationError(
                "The media audio stream could not be inspected. Redownload the source or choose another file."
            )
        try:
            streams = json.loads(result.stdout).get("streams", [])
            stream = streams[0]
            channels = int(stream.get("channels") or 0)
            sample_rate = int(stream.get("sample_rate") or 0)
            duration = float(stream.get("duration") or 0)
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TranscriptValidationError(
                "The media has no usable audio stream for transcription. Redownload the source or choose another file."
            ) from exc
        if channels <= 0 or sample_rate <= 0 or duration <= 0:
            raise TranscriptValidationError(
                "The media audio stream is empty or invalid for transcription. Redownload the source or choose another file."
            )

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
            self.validate_transcription_audio(transcription_input)
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
        if not profane_segments and Path(self.input_file).suffix.lower() == Path(self.output_file).suffix.lower():
            return self._copy_clean_media()
        if not self.ffmpeg_bin:
            self.last_error = "FFmpeg must be available before a censored output can be created."
            print(f"[-] {self.last_error}")
            return False
        os.makedirs(os.path.dirname(os.path.abspath(self.output_file)), exist_ok=True)
        source_has_center_channel = self.has_discrete_center_audio()
        audio_only = self.is_audio_only()
        video_mode = getattr(self, "video_mode", "preserve_source")
        surround_output = getattr(self, "surround_output", "preserve_5_1")
        source_video_codec = "" if audio_only else self.get_video_codec()
        requires_video_encoder = (
            not audio_only
            and video_mode != "preserve_source"
            and source_video_codec != "h264"
        )
        if requires_video_encoder and self.video_encoder is None:
            try:
                self.encoders = available_encoders(self.ffmpeg_bin)
                self.video_encoder = select_working_video_encoder(
                    self.ffmpeg_bin,
                    self.encoders,
                    os.environ.get("CENSOR_VIDEO_ENCODER"),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                self.last_error = f"FFmpeg encoder setup failed: {exc}"
                print(f"[-] {self.last_error}")
                return False
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
            method = self.censor_method
            print(f"[*] Applying censoring (method: {method})...")
        elif source_has_center_channel and surround_output == "downmix_stereo":
            print("[*] No profanity detected. Downmixing surround audio to stereo...")
        else:
            print("[*] No profanity detected. Applying requested output settings...")

        # Karaoke is opt-in. Muting must affect every channel so dialogue cannot
        # remain audible through a surround channel outside the front center.
        use_filter_complex = False
        filter_complex = None
        if profane_segments and self.censor_method == "karaoke":
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

    def _copy_clean_media(self) -> bool:
        """Copy media with no matching policy terms while preserving its verified container."""
        print("[*] No profanity detected. Copying source media without transcoding...")
        source = Path(self.input_file)
        destination = Path(self.output_file)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_size = source.stat().st_size
            copied_bytes = 0
            last_percent = -1.0
            with source.open("rb") as input_file, destination.open("wb") as output_file:
                while True:
                    self._check_cancelled()
                    chunk = input_file.read(1024 * 1024)
                    if not chunk:
                        break
                    output_file.write(chunk)
                    copied_bytes += len(chunk)
                    percent = 100.0 if source_size == 0 else min(100.0, copied_bytes / source_size * 100.0)
                    if percent >= last_percent + 5.0 or percent == 100.0:
                        self._emit_progress("censoring", percent, message="Copying source media")
                        last_percent = percent
            shutil.copystat(source, destination, follow_symlinks=False)
            print(f"[+] Source copied: {self.output_file}")
            return True
        except Exception as exc:
            self.last_error = f"Could not copy source media: {exc}"
            print(f"[-] {self.last_error}")
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

    def verify_output(self) -> None:
        """Check the staged media before the job publishes it or archives its source."""
        self._check_cancelled()
        result = subprocess.run(
            [self.ffprobe_bin, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", self.output_file],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            stream_types = {item.get("codec_type") for item in json.loads(result.stdout).get("streams", [])}
        except (ValueError, TypeError, AttributeError) as exc:
            raise RuntimeError("The processed output could not be verified") from exc
        if result.returncode or "audio" not in stream_types or (not self.is_audio_only() and "video" not in stream_types):
            raise RuntimeError("The processed output is missing readable media streams")

    def process_verified_transcript(self, include_undiscovered: bool = False) -> bool:
        """Create censored output from an already verified transcript without Whisper work."""
        started = time.perf_counter()
        transcript_path = self.get_transcript_path()
        try:
            self._check_cancelled()
            if not transcript_path:
                raise TranscriptValidationError(
                    "A persisted transcript is required before a censored output can be created"
                )
            with Path(transcript_path).open(encoding="utf-8") as transcript_file:
                words_data = validate_transcript_data(
                    json.load(transcript_file),
                    whisper_library=self.whisper_library,
                    whisper_model=self.model_name,
                    require_front_center=self.has_discrete_center_audio(),
                )
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
            self._emit_progress("censoring", 0.0, message="Censoring started")
            success = self.censor_video(profane_segments)
            print(f"[*] Total elapsed: {self._format_seconds(time.perf_counter() - started)}")
            return success
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[-] Censoring failed: {exc}")
            return False



def main():
    """Retain the legacy module entrypoint without loading CLI code during imports."""
    from .cli import main as run_cli

    return run_cli()


if __name__ == "__main__":
    main()
