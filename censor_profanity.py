#!/usr/bin/env python3
"""Compatibility entry point for the packaged censor engine."""

from __future__ import annotations

import sys


if __name__ == "__main__":
    from backend.censor.engine import main

    main()
else:
    from backend.censor import engine as _engine

    sys.modules[__name__] = _engine