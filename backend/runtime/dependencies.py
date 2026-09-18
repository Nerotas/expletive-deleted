"""Compatibility exports; implementation lives in focused sibling modules."""

# Keep existing callers stable while internal code imports its owning module.
from .dependency_inspection import (
    _executable_version,
    inspect_executable,
    inspect_ytdlp,
    inspect_js_runtime,
    _version_is_supported,
    inspect_python_dependencies,
    inspect_whisper_model,
    inspect_dependencies,
    _default_js_runtime_executable,
    require_whisper_model_path,
)
from .dependency_install import (
    _emit,
    _run_action,
    _status_by_id,
    execute_install_plan,
)
from backend.runtime.dependency_errors import (
    DependencyPlanError,
    DependencyConsentError,
    DependencyInstallError,
    DependencyNotReadyError,
)
from .dependency_models import (
    DependencyState,
    InstallKind,
    DependencyStatus,
    _missing_ytdlp_status,
    _missing_js_runtime_status,
    DependencyInventory,
    InstallAction,
    InstallPlan,
    InstallProgress,
    InstallResult,
)
from .dependency_plan import (
    _plan_id,
    build_install_plan,
)
from .dependency_specs import (
    STATIC_FFMPEG_VERSION,
    FFMPEG_VERSION,
    FFMPEG_MINIMUM_VERSION,
    WHISPER_MODEL_ID,
    WHISPER_MODEL_REVISION,
    WHISPER_MODEL_SIZE_BYTES,
    WHISPER_MODEL_FILES,
    WHISPER_MODELS,
    WHISPER_LIBRARIES,
    YTDLP_VERSION,
    YTDLP_RELEASE_URL,
    DENO_VERSION,
    _DENO_ASSET,
    DENO_RELEASE_URL,
    DENO_CHECKSUM_URL,
    PYTHON_DEPENDENCIES,
    PYTHON_REQUIREMENTS,
    _python_dependencies_for_library,
    _python_requirements_for_library,
    _whisper_dependency_id,
    DENO_MINIMUM_VERSION,
)
