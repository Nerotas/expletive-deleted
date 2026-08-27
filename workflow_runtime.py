"""Compatibility alias for :mod:`backend.runtime.environment`."""

import sys

from backend.runtime import environment as _environment


sys.modules[__name__] = _environment