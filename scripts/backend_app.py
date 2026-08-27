#!/usr/bin/env python3
"""Exercise the local backend service before the Electron frontend exists."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.service import BackendService


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("settings", help="Print effective application settings")
    subparsers.add_parser("capabilities", help="Inspect local runtime capabilities")
    subparsers.add_parser("library", help="Scan the configured Ready directory")
    process = subparsers.add_parser("process", help="Submit and wait for one serial media job")
    process.add_argument("source", type=Path)
    process.add_argument("--mode", choices=["report_only", "censor"])
    args = parser.parse_args(argv)

    service = BackendService()
    try:
        if args.command == "settings":
            _print(service.get_settings())
            return 0
        if args.command == "capabilities":
            capabilities = service.get_capabilities()
            _print(capabilities)
            return 0 if capabilities["ready"] else 1
        if args.command == "library":
            _print([item.to_dict() for item in service.get_library()])
            return 0

        job = service.submit_job(args.source, args.mode)
        interrupted = False
        try:
            completed = service.jobs.wait(job.id)
        except KeyboardInterrupt:
            interrupted = True
            service.jobs.cancel(job.id)
            completed = service.jobs.wait(job.id)
        _print(
            {
                "job": completed.to_dict(),
                "events": [event.to_dict() for event in service.jobs.events(job.id)],
            }
        )
        if interrupted:
            return 130
        return 0 if completed.status in ("completed", "transcribed") else 1
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())