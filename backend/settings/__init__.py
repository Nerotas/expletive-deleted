"""Persistent application settings and directory configuration."""

from .directories import DirectoryAccessError, DirectoryStatus, ensure_directories, inspect_directories
from .models import (
    AppSettings,
    AudioSettings,
    CensoringSettings,
    DirectorySettings,
    OnboardingSettings,
    ProcessingSettings,
    RuntimeSettings,
    SettingsValidationError,
    SourceSettings,
    WhisperSettings,
    default_user_data_root,
)
from .resolver import load_effective_settings, resolve_runtime_paths
from .serialization import SETTINGS_SCHEMA_VERSION, settings_from_dict, settings_to_dict
from .store import SettingsFileError, SettingsStore, default_app_data_root, default_settings_path

__all__ = [
    "AppSettings",
    "AudioSettings",
    "CensoringSettings",
    "DirectorySettings",
    "DirectoryAccessError",
    "DirectoryStatus",
    "OnboardingSettings",
    "ProcessingSettings",
    "RuntimeSettings",
    "SettingsValidationError",
    "SETTINGS_SCHEMA_VERSION",
    "SettingsFileError",
    "SettingsStore",
    "SourceSettings",
    "WhisperSettings",
    "default_user_data_root",
    "default_app_data_root",
    "default_settings_path",
    "ensure_directories",
    "inspect_directories",
    "load_effective_settings",
    "resolve_runtime_paths",
    "settings_from_dict",
    "settings_to_dict",
]