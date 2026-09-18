"""Read-only checks for processing tools, Python packages, and model caches."""

from __future__ import annotations

import importlib
import importlib.metadata
import subprocess
from dataclasses import replace
from pathlib import Path
from backend.runtime.locations import (
    resolve_media_tools,
    resolve_ytdlp_path,
    resolve_deno_path,
    get_whisper_cache_dir,
)
from .python_imports import inspect_python_imports
from backend.runtime.dependency_errors import DependencyNotReadyError
from .dependency_models import (
    DependencyInventory,
    DependencyState,
    DependencyStatus,
    _missing_js_runtime_status,
)
from .dependency_specs import (
    DENO_MINIMUM_VERSION,
    DENO_VERSION,
    FFMPEG_MINIMUM_VERSION,
    FFMPEG_VERSION,
    WHISPER_MODEL_FILES,
    WHISPER_MODEL_ID,
    WHISPER_MODEL_REVISION,
    YTDLP_VERSION,
    _python_dependencies_for_library,
    _whisper_dependency_id,
)


def _executable_version(executable: str) -> tuple[str | None, str]:
    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as exc:
        return None, str(exc)
    output = (result.stdout or result.stderr).strip()
    first_line = output.splitlines()[0] if output else "no version output"
    if result.returncode != 0:
        return None, first_line
    fields = first_line.split()
    version = fields[2] if len(fields) >= 3 and fields[1] == "version" else None
    return version, first_line


def inspect_executable(
    dependency_id: str,
    name: str,
    executable: str | None,
    required_version: str | None = None,
) -> DependencyStatus:
    if not executable:
        return DependencyStatus(
            id=dependency_id,
            name=name,
            state="missing",
            required_version=required_version,
            installed_version=None,
            path=None,
            detail=f"{name} was not found",
            install_supported=True,
        )
    version, detail = _executable_version(executable)
    version_supported = bool(version and _version_is_supported(version, required_version))
    if version and not version_supported:
        detail = f"installed {version}; requires {required_version}"
    return DependencyStatus(
        id=dependency_id,
        name=name,
        state="ready" if version_supported else "invalid",
        required_version=required_version,
        installed_version=version,
        path=Path(executable),
        detail=detail,
        install_supported=True,
    )


def inspect_ytdlp(executable: str | None) -> DependencyStatus:
    """Verify the pinned yt-dlp executable using its dedicated version protocol."""
    if not executable:
        return DependencyStatus("ytdlp", "yt-dlp", "missing", YTDLP_VERSION, None, None, "yt-dlp was not found", True)
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except subprocess.TimeoutExpired:
        return DependencyStatus(
            "ytdlp",
            "yt-dlp",
            "invalid",
            YTDLP_VERSION,
            None,
            Path(executable),
            "yt-dlp did not respond to its version check. Reinstall it from System Requirements.",
            True,
        )
    except OSError as exc:
        return DependencyStatus("ytdlp", "yt-dlp", "invalid", YTDLP_VERSION, None, Path(executable), str(exc), True)
    version = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
    detail = f"installed {version}" if version else (result.stderr.strip() or "yt-dlp did not report a version")
    return DependencyStatus("ytdlp", "yt-dlp", "ready" if version == YTDLP_VERSION else "invalid", YTDLP_VERSION, version, Path(executable), detail, True)


def inspect_js_runtime(executable: str | None) -> DependencyStatus:
    """Verify a Deno JavaScript runtime yt-dlp can use to solve YouTube's challenge."""
    if not executable or not Path(executable).is_file():
        return _missing_js_runtime_status()
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return DependencyStatus("js_runtime", "JavaScript runtime", "invalid", DENO_VERSION, None, Path(executable), str(exc), True)
    first_line = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
    version = first_line.split()[1] if first_line and first_line.startswith("deno ") else None
    try:
        parsed = tuple(int(part) for part in version.split(".")[:3]) if version else None
    except ValueError:
        parsed = None
    supported = bool(parsed and parsed >= DENO_MINIMUM_VERSION)
    detail = f"installed {version}" if version else (result.stderr.strip() or "Deno did not report a version")
    if version and not supported:
        detail = f"installed {version}; requires {'.'.join(map(str, DENO_MINIMUM_VERSION))} or later"
    return DependencyStatus("js_runtime", "JavaScript runtime", "ready" if supported else "invalid", DENO_VERSION, version, Path(executable), detail, True)


def _version_is_supported(version: str, required_version: str | None) -> bool:
    """Accept every FFmpeg release at or newer than the supported baseline."""
    if required_version != FFMPEG_VERSION:
        return required_version is None or version.startswith(required_version)
    parts = version.split("-", 1)[0].split(".")
    try:
        parsed = tuple(int(part) for part in parts[:2])
    except ValueError:
        return False
    return parsed >= FFMPEG_MINIMUM_VERSION


def inspect_python_dependencies(
    whisper_library: str = "faster-whisper",
) -> tuple[DependencyStatus, ...]:
    statuses: list[DependencyStatus] = []
    for distribution, required_version in _python_dependencies_for_library(whisper_library):
        try:
            installed_version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            installed_version = None
        state: DependencyState
        if installed_version is None:
            state = "missing"
            detail = f"{distribution} is not installed"
        elif installed_version != required_version:
            state = "invalid"
            detail = f"installed {installed_version}; required {required_version}"
        else:
            state = "ready"
            detail = f"installed {installed_version}"
        statuses.append(
            DependencyStatus(
                id=f"python:{distribution}",
                name=distribution,
                state=state,
                required_version=required_version,
                installed_version=installed_version,
                path=None,
                detail=detail,
                install_supported=True,
            )
        )
    import_errors = inspect_python_imports([status.name for status in statuses if status.ready])
    return tuple(
        replace(
            status,
            state="invalid",
            detail=f"{status.name} could not load: {import_errors[status.name]}. Repair Python packages from setup.",
        ) if status.ready and import_errors.get(status.name) else status
        for status in statuses
    )


def inspect_whisper_model(
    cache_dir: Path | None = None,
    *,
    library: str = "faster-whisper",
    model: str = "large-v3",
) -> DependencyStatus:
    """Verify the selected model without network access."""
    cache_dir = (cache_dir or get_whisper_cache_dir()).resolve()
    dependency_id = _whisper_dependency_id(library, model)
    display_name = f"Whisper {model} model ({library})"
    revision = WHISPER_MODEL_REVISION if model == "large-v3" else None
    try:
        from faster_whisper.utils import download_model

        size_or_id = WHISPER_MODEL_ID if model == "large-v3" else model
        model_path = Path(
            download_model(
                size_or_id,
                cache_dir=str(cache_dir),
                local_files_only=True,
                revision=revision,
            )
        )
    except Exception as exc:
        return DependencyStatus(
            id=dependency_id,
            name=display_name,
            state="missing",
            required_version=revision,
            installed_version=None,
            path=None,
            detail=f"pinned model is not cached: {exc}",
            install_supported=True,
        )

    missing_files = tuple(name for name in WHISPER_MODEL_FILES if not (model_path / name).is_file())
    if missing_files:
        return DependencyStatus(
            id=dependency_id,
            name=display_name,
            state="invalid",
            required_version=revision,
            installed_version=None,
            path=model_path,
            detail=f"model cache is incomplete: {', '.join(missing_files)}",
            install_supported=True,
        )
    return DependencyStatus(
        id=dependency_id,
        name=display_name,
        state="ready",
        required_version=revision,
        installed_version=revision,
        path=model_path,
        detail="pinned model files are cached",
        install_supported=True,
    )


def inspect_dependencies(
    cache_dir: Path | None = None,
    *,
    ffmpeg_bin: str | Path | None = None,
    ffprobe_bin: str | Path | None = None,
    whisper_library: str = "faster-whisper",
    whisper_model: str = "large-v3",
    ytdlp_bin: str | Path | None = None,
    js_runtime_bin: str | Path | None = None,
) -> DependencyInventory:
    """Return dependency state without installing or downloading anything."""
    ffmpeg_bin, ffprobe_bin = resolve_media_tools(ffmpeg_bin, ffprobe_bin)
    return DependencyInventory(
        ffmpeg=inspect_executable(
            "ffmpeg",
            "FFmpeg",
            ffmpeg_bin,
            FFMPEG_VERSION,
        ),
        ffprobe=inspect_executable(
            "ffprobe",
            "FFprobe",
            ffprobe_bin,
            FFMPEG_VERSION,
        ),
        python=inspect_python_dependencies(whisper_library),
        whisper_model=inspect_whisper_model(
            cache_dir,
            library=whisper_library,
            model=whisper_model,
        ),
        ytdlp=inspect_ytdlp(str(resolve_ytdlp_path(Path(ytdlp_bin) if ytdlp_bin else None))),
        js_runtime=inspect_js_runtime(str(js_runtime_bin) if js_runtime_bin else _default_js_runtime_executable()),
    )


def _default_js_runtime_executable() -> str | None:
    """Prefer the app-managed Deno download, falling back to one already on PATH."""
    resolved = resolve_deno_path()
    return str(resolved) if resolved else None


def require_whisper_model_path(
    cache_dir: Path | None = None,
    *,
    library: str = "faster-whisper",
    model: str = "large-v3",
) -> Path:
    """Return the verified selected model path or fail without network access."""
    status = inspect_whisper_model(cache_dir, library=library, model=model)
    if not status.ready or status.path is None:
        raise DependencyNotReadyError(
            f"Whisper {model} ({library}) is not prepared. Install it from the app setup. "
            f"{status.detail}"
        )
    return status.path
