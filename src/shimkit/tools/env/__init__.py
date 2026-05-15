"""``.env`` viewer + scaffolder with secret redaction — ``shimkit env``.

Default-deny view: values are redacted unless ``--reveal`` is passed.
Redaction reuses the same key-name regex shimkit's log layer uses for
JSONL ``extra={}`` payloads, so a developer who's careful with one
sees the other behave the same way.

Pure parser in :mod:`shimkit.tools.env.parser` is text-in / list-out
and unit-testable without I/O.
"""

from __future__ import annotations

from .manager import EnvManager
from .models import EnvEntry, EnvFile

__all__ = ["EnvEntry", "EnvFile", "EnvManager"]
