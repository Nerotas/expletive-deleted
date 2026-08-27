#!/usr/bin/env python3
"""Compatibility entry point for the packaged bootstrap command."""

from scripts.bootstrap import main


if __name__ == "__main__":
    raise SystemExit(main())