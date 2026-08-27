"""Portable runtime support for the profanity censoring workflow."""

from __future__ import annotations

import configparser
import json
import os
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from backend.runtime.paths import (
    PROJECT_ROOT,
    RuntimePaths,
    get_project_root,
    get_runtime_paths as _get_runtime_paths,
)

try:
    import ctranslate2
except ImportError:
    ctranslate2 = None


CONFIG_FILE = PROJECT_ROOT / "config.ini"
ENCODER_PREFERENCE = (
    "h264_nvenc",
    "h264_qsv",
    "h264_videotoolbox",
    "libx264",
)
REQUIRED_WHISPER_MODEL = "large-v3"
SUPPORTED_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")
WHISPER_TIMING_HISTORY_FILE = ".whisper-timing.json"


@dataclass(frozen=True)
class WhisperDeviceStatus:
    requested: str
    selected: str
    compute_type: str
    detail: str


def get_runtime_paths(root: Path | None = None) -> RuntimePaths:
    """Return the processing directories through the legacy runtime API."""
    return _get_runtime_paths(root)


def require_whisper_model(model_name: str) -> str:
    """Validate a supported Whisper model name."""
    normalized = "large-v3" if model_name == "large" else model_name
    if normalized not in SUPPORTED_WHISPER_MODELS:
        raise ValueError(
            f"Unsupported Whisper model {model_name!r}; choose one of: "
            f"{', '.join(SUPPORTED_WHISPER_MODELS)}."
        )
    return normalized


def read_project_config(root: Path | None = None) -> configparser.ConfigParser:
    project_root = get_project_root(root)
    parser = configparser.ConfigParser()
    parser.read(project_root / "config.ini")
    return parser


def get_whisper_cache_dir(root: Path | None = None) -> Path:
    project_root = get_project_root(root)
    configured = os.environ.get("CENSOR_WHISPER_CACHE_DIR", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()

    parser = read_project_config(project_root)
    configured = parser.get("Whisper", "CacheFolder", fallback="whisper-cache").strip()
    candidate = Path(configured).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def get_managed_ffmpeg_manifest_path(root: Path | None = None) -> Path:
    """Return the local manifest written after an approved managed FFmpeg download."""
    return get_whisper_cache_dir(root).parent / "ffmpeg-runtime.json"


def get_managed_ffmpeg_paths(root: Path | None = None) -> tuple[str | None, str | None]:
    """Read the verified, application-managed FFmpeg paths without downloading anything."""
    manifest_path = get_managed_ffmpeg_manifest_path(root)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        ffmpeg = Path(payload["ffmpeg"]).resolve()
        ffprobe = Path(payload["ffprobe"]).resolve()
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, None
    return (str(ffmpeg) if ffmpeg.is_file() else None, str(ffprobe) if ffprobe.is_file() else None)


def get_whisper_timing_history_path(root: Path | None = None) -> Path:
    """Return the local, machine-specific transcription timing history file."""
    return get_project_root(root) / WHISPER_TIMING_HISTORY_FILE


def get_whisper_profile_key(model_name: str = REQUIRED_WHISPER_MODEL) -> str:
    """Identify the selected model and execution profile for timing calibration."""
    status = get_whisper_device_status(model_name)
    return f"{model_name}:{status.selected}:{status.compute_type}"


def get_calibrated_transcription_factor(
    model_name: str = REQUIRED_WHISPER_MODEL, root: Path | None = None
) -> float | None:
    """Return the median recent wall-time/media-time factor for this profile."""
    history_path = get_whisper_timing_history_path(root)
    try:
        records = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    profile_key = get_whisper_profile_key(model_name)
    factors = [
        record.get("seconds_per_media_second")
        for record in records
        if record.get("profile") == profile_key
        and isinstance(record.get("seconds_per_media_second"), (int, float))
        and record["seconds_per_media_second"] > 0
    ]
    return statistics.median(factors[-5:]) if factors else None


def record_transcription_timing(
    media_duration_seconds: float,
    elapsed_seconds: float,
    model_name: str = REQUIRED_WHISPER_MODEL,
    root: Path | None = None,
) -> None:
    """Persist one completed transcription measurement for future local estimates."""
    if media_duration_seconds <= 0 or elapsed_seconds <= 0:
        return

    history_path = get_whisper_timing_history_path(root)
    try:
        records = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            records = []
    except (OSError, json.JSONDecodeError):
        records = []

    records.append(
        {
            "profile": get_whisper_profile_key(model_name),
            "seconds_per_media_second": elapsed_seconds / media_duration_seconds,
        }
    )
    history_path.write_text(json.dumps(records[-20:], indent=2) + "\n", encoding="utf-8")


def get_profanity_exclusions_file(root: Path | None = None) -> Path:
    """Return the configured file containing words excluded from censoring."""
    project_root = get_project_root(root)
    configured = os.environ.get("CENSOR_EXCLUSIONS_FILE", "").strip()
    if not configured:
        parser = read_project_config(project_root)
        configured = parser.get("Profanity", "ExclusionsFile", fallback="").strip()
    if not configured:
        return PROJECT_ROOT / "resources" / "profanity_exclusions.txt"

    candidate = Path(configured).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def get_profanity_censor_words_file(root: Path | None = None) -> Path:
    """Return the configured file containing words to censor."""
    project_root = get_project_root(root)
    configured = os.environ.get("CENSOR_CENSOR_WORDS_FILE", "").strip()
    if not configured:
        parser = read_project_config(project_root)
        configured = parser.get("Profanity", "CensorWordsFile", fallback="").strip()
    if not configured:
        return PROJECT_ROOT / "resources" / "profanity_censor_words.txt"

    candidate = Path(configured).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def load_word_list(word_list_file: Path, description: str) -> set[str]:
    """Load lowercase words from a UTF-8 text file, ignoring comments and blanks."""
    if not word_list_file.is_file():
        raise FileNotFoundError(f"{description} file was not found: {word_list_file}")

    with word_list_file.open(encoding="utf-8-sig") as source:
        return {
            line.partition("#")[0].strip().lower()
            for line in source
            if line.partition("#")[0].strip()
        }


def load_profanity_exclusions(exclusions_file: Path) -> set[str]:
    return load_word_list(exclusions_file, "Profanity exclusions")


def load_profanity_censor_words(censor_words_file: Path) -> set[str]:
    return load_word_list(censor_words_file, "Profanity censor words")


def normalize_policy_word(value: str) -> str:
    """Validate one user-entered policy word or phrase for safe file storage."""
    normalized = " ".join(value.split()).lower()
    if not normalized:
        raise ValueError("A profanity word or phrase is required")
    if len(normalized) > 100:
        raise ValueError("A profanity word or phrase must be 100 characters or fewer")
    if "#" in normalized or any(ord(character) < 32 for character in normalized):
        raise ValueError("A profanity word or phrase cannot contain comments or control characters")
    return normalized


def add_word_to_list(word_list_file: Path, value: str, description: str) -> tuple[set[str], bool]:
    """Append a normalized entry while preserving the user's existing comments and order."""
    word = normalize_policy_word(value)
    words = load_word_list(word_list_file, description)
    if word in words:
        return words, False
    with word_list_file.open("a", encoding="utf-8", newline="\n") as destination:
        if word_list_file.stat().st_size:
            destination.write("\n")
        destination.write(f"{word}\n")
    return words | {word}, True


def remove_word_from_list(word_list_file: Path, value: str, description: str) -> tuple[set[str], bool]:
    """Remove matching policy entries without rewriting unrelated comments or entries."""
    word = normalize_policy_word(value)
    with word_list_file.open(encoding="utf-8-sig", newline="") as source:
        original_lines = source.read().splitlines(keepends=True)
    retained_lines = [
        line for line in original_lines
        if line.partition("#")[0].strip().lower() != word
    ]
    removed = len(retained_lines) != len(original_lines)
    if removed:
        with word_list_file.open("w", encoding="utf-8", newline="") as destination:
            destination.write("".join(retained_lines))
    return load_word_list(word_list_file, description), removed


def get_external_whisper_cache_dir() -> Path:
    default_cache_root = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser()
    return (default_cache_root / "whisper").resolve()


def get_directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(file_path.stat().st_size for file_path in path.rglob("*") if file_path.is_file())


def format_bytes(total_bytes: int) -> str:
    size = float(total_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024


def _find_executable(name: str, environment_variable: str) -> str | None:
    """Find an executable only when it can actually return its version.

    Windows command aliases can be present on disk but fail to launch a usable
    program in a child process, so existence alone is not sufficient here.
    """
    def usable(candidate: Path | str | None) -> str | None:
        if not candidate or not Path(candidate).is_file():
            return None
        candidate_path = str(candidate)
        try:
            result = subprocess.run(
                [candidate_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return candidate_path if result.returncode == 0 and (result.stdout or result.stderr).strip() else None

    configured_path = os.environ.get(environment_variable)
    if configured_path:
        return usable(Path(configured_path).expanduser())
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_packages.is_dir():
                candidates = sorted(
                    (candidate for candidate in winget_packages.rglob(f"{name}.exe") if candidate.is_file()),
                    key=lambda candidate: str(candidate).casefold(),
                    reverse=True,
                )
                for candidate in candidates:
                    if resolved := usable(candidate):
                        return resolved

            winget_alias = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe"
            if resolved := usable(winget_alias):
                return resolved

    path_executable = shutil.which(name)
    if resolved := usable(path_executable):
        return resolved

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            windows_apps_alias = Path(local_app_data) / "Microsoft" / "WindowsApps" / f"{name}.exe"
            if resolved := usable(windows_apps_alias):
                return resolved
    return None


def find_ffmpeg() -> str | None:
    """Find configured or app-managed FFmpeg before falling back to the system."""
    configured = os.environ.get("CENSOR_FFMPEG")
    if configured:
        return _find_executable("ffmpeg", "CENSOR_FFMPEG")
    return get_managed_ffmpeg_paths()[0] or _find_executable("ffmpeg", "CENSOR_FFMPEG")


def find_ffprobe() -> str | None:
    """Find configured or app-managed FFprobe before falling back to the system."""
    configured = os.environ.get("CENSOR_FFPROBE")
    if configured:
        return _find_executable("ffprobe", "CENSOR_FFPROBE")
    return get_managed_ffmpeg_paths()[1] or _find_executable("ffprobe", "CENSOR_FFPROBE")


def ensure_executable_directory_on_path(executable_path: str | None) -> None:
    """Prepend an executable directory to PATH so subprocesses can resolve it by name."""
    if not executable_path:
        return

    directory = str(Path(executable_path).resolve().parent)
    current_path = os.environ.get("PATH", "")
    entries = current_path.split(os.pathsep) if current_path else []
    normalized = {os.path.normcase(os.path.normpath(entry)) for entry in entries if entry}
    if os.path.normcase(os.path.normpath(directory)) in normalized:
        return

    os.environ["PATH"] = directory if not current_path else f"{directory}{os.pathsep}{current_path}"


def get_cuda_memory_mib() -> int | None:
    """Return total memory for the first NVIDIA GPU when nvidia-smi is available."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    result = subprocess.run(
        [nvidia_smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return int(result.stdout.splitlines()[0].strip())
    except ValueError:
        return None


def get_whisper_device_status(
    model_name: str = REQUIRED_WHISPER_MODEL,
    requested_device: str | None = None,
) -> WhisperDeviceStatus:
    """Select a safe CTranslate2 profile for the requested Whisper model."""
    model_name = require_whisper_model(model_name)
    parser = read_project_config()
    configured_device = parser.get("Whisper", "Device", fallback="auto").strip().lower()
    requested = os.environ.get(
        "CENSOR_WHISPER_DEVICE",
        requested_device or configured_device,
    ).strip().lower()
    requested = requested if requested in {"auto", "cpu", "cuda"} else "auto"
    configured_compute = parser.get("Whisper", "ComputeType", fallback="auto").strip().lower()
    requested_compute = os.environ.get("CENSOR_WHISPER_COMPUTE_TYPE", configured_compute).strip().lower()

    if requested == "cpu":
        return WhisperDeviceStatus("cpu", "cpu", "int8", "CPU was explicitly requested.")

    if ctranslate2 is not None:
        try:
            if ctranslate2.get_cuda_device_count() > 0:
                supported = ctranslate2.get_supported_compute_types("cuda", 0)
                candidates = ("float16", "int8_float16", "int8_float32", "int8", "float32")
                compute_type = requested_compute if requested_compute in supported else next(
                    (candidate for candidate in candidates if candidate in supported), None
                )
                if compute_type:
                    memory_mib = get_cuda_memory_mib()
                    minimum_memory = {
                        "tiny": 2048,
                        "base": 2048,
                        "small": 4096,
                        "medium": 6144,
                        "large-v3": 8192,
                    }.get(model_name, 8192)
                    if requested == "cuda" or memory_mib is None or memory_mib >= minimum_memory:
                        detail = f"CUDA selected with {compute_type}."
                        if memory_mib is not None:
                            detail = f"CUDA selected with {compute_type} on {memory_mib} MiB VRAM."
                        return WhisperDeviceStatus(requested, "cuda", compute_type, detail)
                    return WhisperDeviceStatus(
                        requested,
                        "cpu",
                        "int8",
                        (
                            f"CUDA GPU has {memory_mib} MiB VRAM; Whisper {model_name} needs at least "
                            f"{minimum_memory} MiB. Using CPU int8."
                        ),
                    )
        except Exception:
            pass

    detail = "CUDA is unavailable; using CPU int8."
    if requested == "cuda":
        detail = "CUDA was explicitly requested but is unavailable; using CPU int8."
    return WhisperDeviceStatus(requested, "cpu", "int8", detail)


def available_encoders(ffmpeg_bin: str) -> set[str]:
    """Return video encoders reported by the installed FFmpeg binary."""
    result = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()

    encoders = set()
    for line in (result.stdout + result.stderr).splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].startswith("V") and fields[1] != "=":
            encoders.add(fields[1])
    return encoders


def select_video_encoder(
    encoders: Iterable[str], override: str | None = None
) -> str:
    """Choose a supported H.264 encoder, honoring an explicit override."""
    available = set(encoders)
    if override:
        if override not in available:
            raise ValueError(f"Requested video encoder is unavailable: {override}")
        return override

    for encoder in ENCODER_PREFERENCE:
        if encoder in available:
            return encoder
    raise RuntimeError("FFmpeg does not provide a supported H.264 encoder")


@lru_cache(maxsize=None)
def video_encoder_runtime_available(ffmpeg_bin: str, encoder: str) -> bool:
    """Return whether an encoder can produce a frame on the current machine."""
    try:
        result = subprocess.run(
            [
                ffmpeg_bin,
                "-v", "error",
                "-f", "lavfi",
                "-i", "testsrc2=size=128x128:rate=1",
                "-frames:v", "1",
                "-c:v", encoder,
                "-f", "null",
                "-",
            ],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def select_working_video_encoder(
    ffmpeg_bin: str,
    encoders: Iterable[str],
    override: str | None = None,
) -> str:
    """Choose the preferred encoder that is usable on the current machine."""
    available = set(encoders)
    if override:
        selected = select_video_encoder(available, override)
        if not video_encoder_runtime_available(ffmpeg_bin, selected):
            raise RuntimeError(f"Requested video encoder cannot run on this machine: {selected}")
        return selected

    for encoder in ENCODER_PREFERENCE:
        if encoder in available and video_encoder_runtime_available(ffmpeg_bin, encoder):
            return encoder
    raise RuntimeError("FFmpeg does not provide a working H.264 encoder")
