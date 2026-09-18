"""Application paths, configured tool resolution, and legacy word-list helpers."""

from __future__ import annotations

import configparser
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from backend.application_identity import get_app_data_root
from backend.runtime.paths import (
    PROJECT_ROOT,
    RuntimePaths,
    get_project_root,
    get_runtime_paths as _get_runtime_paths,
)


CONFIG_FILE = PROJECT_ROOT / "config.ini"

REQUIRED_WHISPER_MODEL = "large-v3"

SUPPORTED_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")


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


def get_application_runtime_root(
    environment: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the per-user directory for explicitly approved runtime assets."""
    environment = os.environ if environment is None else environment
    configured = environment.get("CENSOR_RUNTIME_ASSETS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = environment.get("LOCALAPPDATA", "")
    venv_configuration = Path(sys.prefix) / "pyvenv.cfg"
    try:
        venv_origin = venv_configuration.read_text(encoding="utf-8")
    except OSError:
        venv_origin = ""
    windows_store_python = (
        "WindowsApps" in str(sys.executable)
        or "LocalCache" in str(Path.home())
        or ("\\packages\\" in local_app_data.casefold() and "\\localcache" in local_app_data.casefold())
        or "\\windowsapps\\" in venv_origin.casefold()
    )
    if windows_store_python and platform.system() == "Windows":
        stable_root = (Path.home() / ".expletive-deleted" / "runtime").expanduser().resolve()
        return stable_root

    return get_app_data_root(environment, home)


def get_managed_whisper_cache_dir(root: Path | None = None) -> Path:
    """Return the app-owned cache root without creating or downloading anything."""
    runtime_root = (root or get_application_runtime_root()).expanduser().resolve()
    return runtime_root / "models" / "whisper"


def resolve_whisper_cache_dir(configured: Path | None = None) -> Path:
    """Resolve settings-driven model storage without changing legacy CLI defaults."""
    # Always pass this path to processing so readiness and model loading agree.
    return (configured if configured is not None else get_managed_whisper_cache_dir()).expanduser().resolve()


def get_managed_python_packages_directory(root: Path | None = None) -> Path:
    """Return the writable per-user target for approved Python packages."""
    runtime_root = (root or get_application_runtime_root()).expanduser().resolve()
    return runtime_root / "dependencies" / "python"


def get_managed_ffmpeg_directory(root: Path | None = None) -> Path:
    """Return the app-owned FFmpeg directory outside the installed application."""
    runtime_root = (root or get_application_runtime_root()).expanduser().resolve()
    return runtime_root / "dependencies" / "ffmpeg"


def get_managed_ytdlp_path(root: Path | None = None) -> Path:
    """Return the approved per-user yt-dlp location without downloading it."""
    runtime_root = (root or get_application_runtime_root()).expanduser().resolve()
    return runtime_root / "dependencies" / "yt-dlp" / "yt-dlp.exe"


def get_managed_deno_path(root: Path | None = None) -> Path:
    """Return the approved per-user Deno location without downloading it."""
    runtime_root = (root or get_application_runtime_root()).expanduser().resolve()
    return runtime_root / "dependencies" / "deno" / "deno.exe"


def resolve_ytdlp_path(configured: Path | None = None) -> Path:
    """Runtime overrides select existing tools, never installation destinations."""
    override = configured or os.environ.get("CENSOR_YTDLP", "").strip()
    return Path(override).expanduser().resolve() if override else get_managed_ytdlp_path()


def resolve_deno_path() -> Path | None:
    """Use the same Deno selection for readiness and every yt-dlp invocation."""
    override = os.environ.get("CENSOR_DENO", "").strip()
    candidate = Path(override).expanduser().resolve() if override else get_managed_deno_path()
    if candidate.is_file():
        return candidate
    on_path = shutil.which("deno")
    return Path(on_path).resolve() if on_path else None


def get_managed_ffmpeg_manifest_path(root: Path | None = None) -> Path:
    """Return the local manifest written after an approved managed FFmpeg download."""
    runtime_root = (root or get_application_runtime_root()).expanduser().resolve()
    return runtime_root / "ffmpeg-runtime.json"


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
    """Prefer the app-managed FFmpeg runtime, then a compatible user installation."""
    configured = os.environ.get("CENSOR_FFMPEG")
    if configured:
        return _find_executable("ffmpeg", "CENSOR_FFMPEG")
    return get_managed_ffmpeg_paths()[0] or _find_executable("ffmpeg", "CENSOR_FFMPEG")


def find_ffprobe() -> str | None:
    """Prefer the app-managed FFprobe runtime, then a compatible user installation."""
    configured = os.environ.get("CENSOR_FFPROBE")
    if configured:
        return _find_executable("ffprobe", "CENSOR_FFPROBE")
    return get_managed_ffmpeg_paths()[1] or _find_executable("ffprobe", "CENSOR_FFPROBE")


def resolve_media_tools(
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
) -> tuple[str | None, str | None]:
    """Honor each configured tool independently before automatic discovery."""
    return (
        str(ffmpeg) if ffmpeg is not None else find_ffmpeg(),
        str(ffprobe) if ffprobe is not None else find_ffprobe(),
    )


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
