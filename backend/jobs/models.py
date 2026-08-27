"""Transport-independent records for backend media jobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


JobMode = Literal["report_only", "censor"]
JobStatus = Literal[
    "queued",
    "transcribing",
    "transcribed",
    "awaiting_review",
    "censoring",
    "verifying",
    "completed",
    "failed",
    "cancelled",
]


@dataclass(frozen=True)
class JobError:
    code: str
    message: str
    detail: str | None = None
    retryable: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class JobRecord:
    id: str
    source: Path
    mode: JobMode
    status: JobStatus = "queued"
    progress_percent: float | None = None
    error: JobError | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Job id must not be empty")
        if not self.source.is_absolute():
            raise ValueError("Job source must be an absolute path")
        if self.progress_percent is not None and not 0 <= self.progress_percent <= 100:
            raise ValueError("Job progress must be from 0 through 100")
        if self.status == "failed" and self.error is None:
            raise ValueError("Failed jobs require an error")
        if self.status != "failed" and self.error is not None:
            raise ValueError("Only failed jobs may contain an error")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source": str(self.source),
            "mode": self.mode,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "error": self.error.to_dict() if self.error else None,
        }