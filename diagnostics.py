#!/usr/bin/env python3
"""Compatibility entry point for packaged runtime diagnostics."""

from scripts.diagnostics import main


if __name__ == "__main__":
    raise SystemExit(main())