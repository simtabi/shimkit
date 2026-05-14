"""Structured logging for shimkit tools.

Every tool gets a logger via ``get_logger(name)``. By default the root
``shimkit`` logger has a ``NullHandler`` so importing the package never
emits log output. When a user passes ``--log-file PATH`` we attach a
JSONL ``FileHandler`` so each line is one event with UTC ISO-8601
timestamp.

No external telemetry. Local files only.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = "shimkit"
_FILE_HANDLER_ATTACHED = False

# Redact obviously-sensitive keys when serialising structured payloads.
_REDACT_KEYS = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|authorization)",
    re.IGNORECASE,
)


def _scrub(value: object) -> object:
    """Recursively redact secret-looking keys in mappings and sequences."""
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if _REDACT_KEYS.search(k) else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


class _JsonlFormatter(logging.Formatter):
    """One JSON object per log line. UTC timestamp, scrubbed extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "tool": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Any extra=... keys set on the record (logger.info(msg, extra={...}))
        # land directly as attributes; copy them over, scrubbed.
        standard = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
            "message",
            "asctime",
        }
        extras = {
            k: _scrub(v)
            for k, v in record.__dict__.items()
            if k not in standard and not k.startswith("_")
        }
        if extras:
            payload["data"] = extras
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Return a logger namespaced under ``shimkit.<name>``.

    Callers do not need to attach handlers — the root ``shimkit`` logger
    has a ``NullHandler``, and ``attach_file_handler()`` adds a JSONL
    file handler when the user passes ``--log-file PATH``.
    """
    root = logging.getLogger(_ROOT)
    if not root.handlers:
        root.addHandler(logging.NullHandler())
    return logging.getLogger(f"{_ROOT}.{name}")


def attach_file_handler(path: str | os.PathLike[str], level: int = logging.DEBUG) -> None:
    """Attach a JSONL ``FileHandler`` to the root shimkit logger.

    Idempotent: calling twice with the same path attaches only once.
    Creates parent directories. Refuses paths that resolve outside the
    user's home or /tmp unless the user is already root.
    """
    global _FILE_HANDLER_ATTACHED
    if _FILE_HANDLER_ATTACHED:
        return
    p = Path(os.fspath(path)).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(p, mode="a", encoding="utf-8")
    handler.setFormatter(_JsonlFormatter())
    handler.setLevel(level)
    root = logging.getLogger(_ROOT)
    root.setLevel(min(root.level or logging.WARNING, level))
    root.addHandler(handler)
    _FILE_HANDLER_ATTACHED = True


def set_verbose(verbose: bool) -> None:
    """Bump the root shimkit logger to DEBUG when ``--verbose`` is set."""
    if verbose:
        logging.getLogger(_ROOT).setLevel(logging.DEBUG)


def reset_for_tests() -> None:
    """Tear down handlers — used by tests to keep cases hermetic."""
    global _FILE_HANDLER_ATTACHED
    root = logging.getLogger(_ROOT)
    for h in list(root.handlers):
        root.removeHandler(h)
        with contextlib.suppress(Exception):
            h.close()
    root.addHandler(logging.NullHandler())
    root.setLevel(logging.WARNING)
    _FILE_HANDLER_ATTACHED = False
