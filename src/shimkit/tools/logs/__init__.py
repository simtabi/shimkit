"""System log tail / grep — ``shimkit logs``.

Read-only tool with no mutators. macOS routes through ``log show`` /
``log stream`` (Apple's Unified Logging); Linux routes through
``journalctl``. Predicate syntax is per-platform and passed through
verbatim.
"""

from __future__ import annotations

from .manager import LogsManager

__all__ = ["LogsManager"]
