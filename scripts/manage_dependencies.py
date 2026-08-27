#!/usr/bin/env python3
"""Inspect, plan, and explicitly approve dependency setup operations."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from backend.runtime import (
    DependencyConsentError,
    DependencyInstallError,
    DependencyPlanError,
    InstallPlan,
    InstallProgress,
    build_install_plan,
    execute_install_plan,
    format_bytes,
    get_whisper_cache_dir,
    inspect_dependencies,
)


COMPONENTS = ("ffmpeg", "python", "whisper_model")


def _status_dict(status) -> dict[str, object]:
    payload = asdict(status)
    payload["path"] = str(status.path) if status.path else None
    return payload


def _inventory_dict(inventory) -> dict[str, object]:
    return {
        "ready": inventory.ready,
        "ffmpeg": _status_dict(inventory.ffmpeg),
        "ffprobe": _status_dict(inventory.ffprobe),
        "python": [_status_dict(status) for status in inventory.python],
        "whisper_model": _status_dict(inventory.whisper_model),
    }


def _plan_dict(plan: InstallPlan) -> dict[str, object]:
    return {
        "plan_id": plan.id,
        "actions": [
            {
                "id": action.id,
                "dependencies": action.dependency_ids,
                "description": action.description,
                "source_name": action.source_name,
                "source_url": action.source_url,
                "command": action.command,
                "estimated_download_bytes": action.estimated_download_bytes,
            }
            for action in plan.actions
        ],
    }


def _default_components() -> list[str]:
    inventory = inspect_dependencies()
    components: list[str] = []
    if not inventory.ffmpeg.ready or not inventory.ffprobe.ready:
        components.append("ffmpeg")
    if any(not status.ready for status in inventory.python):
        components.append("python")
    if not inventory.whisper_model.ready:
        components.append("whisper_model")
    return components


def _components(args: argparse.Namespace) -> list[str]:
    return args.component or _default_components()


def _progress(event: InstallProgress) -> None:
    detail = event.message
    if event.completed_bytes is not None:
        total = f" / {format_bytes(event.total_bytes)}" if event.total_bytes else ""
        detail = f"{detail}: {format_bytes(event.completed_bytes)}{total}"
    print(f"[{event.phase.upper()}] {event.action_id}: {detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="Inspect dependencies without installing anything")
    status.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    for command, help_text in (
        ("plan", "Display sources, versions, commands, and approval ID"),
        ("install", "Execute an exactly approved dependency plan"),
    ):
        operation = subparsers.add_parser(command, help=help_text)
        operation.add_argument(
            "--component",
            action="append",
            choices=COMPONENTS,
            help="Component to include; repeat for multiple components",
        )
        if command == "install":
            operation.add_argument(
                "--approve",
                required=True,
                help="Exact plan ID displayed by the plan command",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cache_dir = get_whisper_cache_dir().resolve()
    if args.command == "status":
        inventory = inspect_dependencies(cache_dir)
        if args.json:
            print(json.dumps(_inventory_dict(inventory), indent=2))
        else:
            for status in (inventory.ffmpeg, inventory.ffprobe, *inventory.python, inventory.whisper_model):
                print(f"[{status.state.upper()}] {status.name}: {status.detail}")
        return 0 if inventory.ready else 1

    components = _components(args)
    if not components:
        print("All dependencies are ready; no install plan is needed.")
        return 0
    try:
        plan = build_install_plan(components, cache_dir=cache_dir)
        if args.command == "plan":
            print(json.dumps(_plan_dict(plan), indent=2))
            print(f"Approve this exact plan with: --approve {plan.id}")
            return 0
        results = execute_install_plan(
            plan,
            approved_plan_id=args.approve,
            progress_callback=_progress,
            cache_dir=cache_dir,
        )
    except (DependencyPlanError, DependencyConsentError, DependencyInstallError) as exc:
        print(f"[FAILED] {exc}")
        return 1

    for result in results:
        print(f"[OK] {result.action_id}: {result.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())