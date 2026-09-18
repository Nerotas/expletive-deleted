"""Supported component versions, download identities, and package requirements."""

from __future__ import annotations

from backend.runtime.dependency_errors import DependencyPlanError


STATIC_FFMPEG_VERSION = "3.0"

FFMPEG_VERSION = "8.0 or later"

FFMPEG_MINIMUM_VERSION = (8, 0)

WHISPER_MODEL_ID = "Systran/faster-whisper-large-v3"

WHISPER_MODEL_REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"

WHISPER_MODEL_SIZE_BYTES = 3_090_835_702

WHISPER_MODEL_FILES = (
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
)

WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")

WHISPER_LIBRARIES = ("faster-whisper",)

YTDLP_VERSION = "2026.08.19"

YTDLP_RELEASE_URL = f"https://github.com/yt-dlp/yt-dlp/releases/download/{YTDLP_VERSION}/yt-dlp.exe"


# yt-dlp shells out to this to solve YouTube's JavaScript ("n") challenge; see https://github.com/yt-dlp/yt-dlp/wiki/EJS
DENO_VERSION = "2.9.6"

_DENO_ASSET = "deno-x86_64-pc-windows-msvc.zip"

DENO_RELEASE_URL = f"https://github.com/denoland/deno/releases/download/v{DENO_VERSION}/{_DENO_ASSET}"

DENO_CHECKSUM_URL = f"{DENO_RELEASE_URL}.sha256sum"

PYTHON_DEPENDENCIES = (
    ("faster-whisper", "1.2.1"),
    ("better-profanity", "0.7.0"),
    ("numpy", "2.5.2"),
    ("ctranslate2", "4.8.1"),
    ("av", "18.1.0"),
    ("huggingface-hub", "1.28.0"),
)

PYTHON_REQUIREMENTS = tuple(f"{name}=={version}" for name, version in PYTHON_DEPENDENCIES)


def _python_dependencies_for_library(
    whisper_library: str,
) -> tuple[tuple[str, str], ...]:
    if whisper_library != "faster-whisper":
        raise DependencyPlanError("Only faster-whisper is supported")
    return PYTHON_DEPENDENCIES


def _python_requirements_for_library(whisper_library: str) -> tuple[str, ...]:
    return tuple(
        f"{distribution}=={version}"
        for distribution, version in _python_dependencies_for_library(whisper_library)
    )


def _whisper_dependency_id(library: str, model: str) -> str:
    return "whisper:large-v3" if (library, model) == ("faster-whisper", "large-v3") else f"whisper:{library}:{model}"


# Deno's own EJS setup guide states 2.3.0 as the minimum version that can run yt-dlp's challenge-solver scripts.
DENO_MINIMUM_VERSION = (2, 3, 0)
