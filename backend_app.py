#!/usr/bin/env python3
"""Compatibility entry point for the local backend application service."""

from scripts.backend_app import main


if __name__ == "__main__":
    raise SystemExit(main())