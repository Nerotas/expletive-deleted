"""Atomic persistence for application settings."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

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
    environment = os.environ if environment is None else environment
    configured = environment.get("CENSOR_APP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return (Path(local_app_data).expanduser() / "ProfanityCensor").resolve()

    home = (home or Path.home()).expanduser()
    xdg_config_home = environment.get("XDG_CONFIG_HOME", "").strip()
    config_root = Path(xdg_config_home).expanduser() if xdg_config_home else home / ".config"
    return (config_root / "profanity-censor").resolve()


def default_settings_path(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    return default_app_data_root(environment, home) / "settings" / "settings.json"


class SettingsStore:
    """Load and atomically save one application settings document."""

    def __init__(self, path: Path | None = None, defaults: AppSettings | None = None):
        self.path = (path or default_settings_path()).expanduser().resolve()
        self.defaults = defaults or AppSettings.defaults()

    def load(self) -> AppSettings:
        if not self.path.exists():
            self.defaults.validate()
            return self.defaults

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return settings_from_dict(raw, self.defaults)
        except json.JSONDecodeError as exc:
            raise SettingsFileError(self.path, f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
        except SettingsValidationError as exc:
            raise SettingsFileError(self.path, str(exc)) from exc
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
                json.dump(payload, temporary_file, indent=2)
                temporary_file.write("\n")
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