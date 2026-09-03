"""Transport-independent records for backend media jobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


JobMode = Literal["report_only", "censor"]
JobSubmissionCode = Literal[
    "already_queued",
    "existing_output",
    "invalid_mode",
    "outside_input",
    "unavailable",
    "unsupported",
]
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
    diagnostic: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "retryable": self.retryable,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class JobRecord:
    id: str
    source: Path
    mode: JobMode
    status: JobStatus = "queued"
    progress_percent: float | None = None
    error: JobError | None = None
    force_transcribe: bool = False
    overwrite_output: bool = False

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
        if self.force_transcribe and self.mode != "report_only":
            raise ValueError("Only report-only jobs can force a fresh transcript")
        if self.overwrite_output and self.mode != "censor":
            raise ValueError("Only censor jobs can replace an existing output")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source": str(self.source),
            "mode": self.mode,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "error": self.error.to_dict() if self.error else None,
            "force_transcribe": self.force_transcribe,
            "overwrite_output": self.overwrite_output,
        }


@dataclass(frozen=True)
class JobSubmissionResult:
    """One ordered result from a selective queue submission."""

    source: Path
    status: Literal["queued", "rejected"]
    job: JobRecord | None = None
    code: JobSubmissionCode | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not self.source.is_absolute():
            raise ValueError("Submission source must be an absolute path")
        if self.status == "queued" and (self.job is None or self.code or self.detail):
            raise ValueError("Queued submissions require only a job")
        if self.status == "rejected" and (self.job is not None or not self.code or not self.detail):
            raise ValueError("Rejected submissions require a code and detail")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "source": str(self.source),
            "status": self.status,
        }
        if self.job is not None:
            result["job"] = self.job.to_dict()
        if self.code is not None:
            result["code"] = self.code
        if self.detail is not None:
            result["detail"] = self.detail
        return result
