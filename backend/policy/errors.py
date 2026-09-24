"""Safe, actionable dictionary persistence failures."""

from pathlib import Path


class PolicyFileError(RuntimeError):
    """Raised when the local user dictionary cannot be safely read or written."""

    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"Dictionary file {path}: {detail}")


class PolicyRecoveryError(PolicyFileError):
    code = "dictionary_recovery_required"
