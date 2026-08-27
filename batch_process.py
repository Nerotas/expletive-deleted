#!/usr/bin/env python3
"""Compatibility entry point for packaged batch orchestration."""

from __future__ import annotations

import sys


if __name__ == "__main__":
    from backend.jobs.batch import main

    raise SystemExit(main())
else:
    from backend.jobs import batch as _batch

    sys.modules[__name__] = _batch