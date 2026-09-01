"""Atomic persistence for application settings."""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from backend.application_identity import get_app_data_root, prepare_app_data_root

from .models import AppSettings, SettingsValidationError
from .serialization import settings_from_dict, settings_to_dict


class SettingsFileError(RuntimeError):
    """Raised when a settings file cannot be read or written safely."""

    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"Settings file {path}: {detail}")


def default_app_data_root(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the internal application-data root for this machine."""
    return get_app_data_root(environment, home)


def default_settings_path(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    return default_app_data_root(environment, home) / "settings.ini"


class SettingsStore:
    """Load and atomically save one user-editable INI settings document."""

    def __init__(self, path: Path | None = None, defaults: AppSettings | None = None):
        self.path = (path or prepare_app_data_root() / "settings.ini").expanduser().resolve()
        self.defaults = defaults or AppSettings.defaults()

    def load(self) -> AppSettings:
        if not self.path.exists():
            legacy_path = self.path.with_name("settings.json")
            if legacy_path.exists():
                settings = self._load_legacy_json(legacy_path)
                self.save(settings)
                return settings
            self.defaults.validate()
            self.save(self.defaults)
            return self.defaults

        try:
            parser = configparser.ConfigParser(interpolation=None)
            with self.path.open(encoding="utf-8") as settings_file:
                parser.read_file(settings_file)
            return settings_from_dict(_settings_from_ini(parser), self.defaults)
        except SettingsValidationError as exc:
            raise SettingsFileError(self.path, str(exc)) from exc
        except (configparser.Error, ValueError) as exc:
            raise SettingsFileError(self.path, f"invalid INI: {exc}") from exc
        except OSError as exc:
            raise SettingsFileError(self.path, str(exc)) from exc

    def save(self, settings: AppSettings) -> Path:
        payload = settings_to_dict(settings)
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                parser = _settings_to_ini(payload)
                parser.write(temporary_file)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, self.path)
            temporary_path = None
            return self.path
        except OSError as exc:
            raise SettingsFileError(self.path, str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def reset(self) -> AppSettings:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise SettingsFileError(self.path, str(exc)) from exc
        return self.defaults

    def _load_legacy_json(self, path: Path) -> AppSettings:
        """Read the pre-INI file once so existing user choices are retained."""
        try:
            return settings_from_dict(json.loads(path.read_text(encoding="utf-8")), self.defaults)
        except json.JSONDecodeError as exc:
            raise SettingsFileError(path, f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
        except (SettingsValidationError, OSError) as exc:
            raise SettingsFileError(path, str(exc)) from exc


_INI_SECTIONS = (
    "directories",
    "processing",
    "censoring",
    "audio",
    "video",
    "whisper",
    "source",
    "runtime",
)
_INI_BOOLEAN_FIELDS = {("source", "archive_after_success"), ("source", "scan_subdirectories")}
_INI_INTEGER_FIELDS = {("censoring", "padding_before_ms"), ("censoring", "padding_after_ms")}


def _settings_from_ini(parser: configparser.ConfigParser) -> dict[str, object]:
    allowed_sections = {"settings", *_INI_SECTIONS}
    unknown_sections = sorted(set(parser.sections()) - allowed_sections)
    if unknown_sections:
        raise ValueError(f"unknown section(s): {', '.join(unknown_sections)}")
    if parser.defaults():
        raise ValueError("the DEFAULT section is not supported")
    if not parser.has_section("settings"):
        raise ValueError("missing [settings] section")

    metadata = dict(parser.items("settings"))
    if set(metadata) != {"schema_version"}:
        raise ValueError("[settings] must contain only schema_version")
    try:
        result: dict[str, object] = {"schema_version": int(metadata["schema_version"])}
    except ValueError as exc:
        raise ValueError("settings.schema_version must be an integer") from exc

    for section in _INI_SECTIONS:
        values: dict[str, object] = {}
        if parser.has_section(section):
            for key, value in parser.items(section):
                if (section, key) in _INI_BOOLEAN_FIELDS:
                    try:
                        values[key] = parser.getboolean(section, key)
                    except ValueError as exc:
                        raise ValueError(f"{section}.{key} must be a boolean") from exc
                elif (section, key) in _INI_INTEGER_FIELDS:
                    try:
                        values[key] = int(value)
                    except ValueError as exc:
                        raise ValueError(f"{section}.{key} must be an integer") from exc
                elif section == "runtime" and key in {"ffmpeg_path", "ffprobe_path", "whisper_cache"} and not value.strip():
                    values[key] = None
                else:
                    values[key] = value
        result[section] = values
    return result


def _settings_to_ini(payload: dict[str, object]) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser["settings"] = {"schema_version": str(payload["schema_version"])}
    for section in _INI_SECTIONS:
        values = payload[section]
        assert isinstance(values, dict)
        parser[section] = {key: "" if value is None else str(value).lower() if isinstance(value, bool) else str(value) for key, value in values.items()}
    return parser
