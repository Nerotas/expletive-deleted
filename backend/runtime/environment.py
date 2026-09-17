"""Compatibility exports; implementation lives in focused sibling modules."""

# Keep existing callers stable while internal code imports its owning module.
from .devices import (
    WhisperDeviceStatus,
    get_cuda_memory_mib,
    get_whisper_device_status,
)
from .encoders import (
    ENCODER_PREFERENCE,
    available_encoders,
    select_video_encoder,
    video_encoder_runtime_available,
    select_working_video_encoder,
)
from .locations import (
    CONFIG_FILE,
    REQUIRED_WHISPER_MODEL,
    SUPPORTED_WHISPER_MODELS,
    get_runtime_paths,
    require_whisper_model,
    read_project_config,
    get_whisper_cache_dir,
    get_application_runtime_root,
    get_managed_whisper_cache_dir,
    resolve_whisper_cache_dir,
    get_managed_python_packages_directory,
    get_managed_ffmpeg_directory,
    get_managed_ytdlp_path,
    get_managed_deno_path,
    resolve_ytdlp_path,
    resolve_deno_path,
    get_managed_ffmpeg_manifest_path,
    get_managed_ffmpeg_paths,
    get_profanity_exclusions_file,
    get_profanity_censor_words_file,
    load_word_list,
    load_profanity_exclusions,
    load_profanity_censor_words,
    normalize_policy_word,
    add_word_to_list,
    remove_word_from_list,
    get_external_whisper_cache_dir,
    get_directory_size,
    format_bytes,
    _find_executable,
    find_ffmpeg,
    find_ffprobe,
    resolve_media_tools,
    ensure_executable_directory_on_path,
)
from .timing import (
    WHISPER_TIMING_HISTORY_FILE,
    get_whisper_timing_history_path,
    get_whisper_profile_key,
    get_calibrated_transcription_factor,
    record_transcription_timing,
)

from .paths import PROJECT_ROOT, RuntimePaths, get_project_root
