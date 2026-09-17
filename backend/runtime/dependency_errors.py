"""Shared setup error contracts without discovery or installation side effects."""


class DependencyPlanError(ValueError):
    """Raised when a dependency install plan cannot be created."""


class DependencyConsentError(PermissionError):
    """Raised unless the caller approves the exact immutable plan."""


class DependencyInstallError(RuntimeError):
    """Raised when installation, cancellation, or verification fails."""


class DependencyNotReadyError(RuntimeError):
    """Raised when processing requests an unprepared dependency."""
