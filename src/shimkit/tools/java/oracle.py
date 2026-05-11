"""Remove Oracle JDK artifacts from macOS system paths.

Glob patterns and safe-root validation paths come from
``config.tools.java.oracle_glob_patterns`` and
``config.tools.java.oracle_safe_roots``. Every matched path is checked
against the safe-root list before deletion — a defence-in-depth guard
that survives even a misconfigured glob.
"""

from __future__ import annotations

import glob
from pathlib import Path

from shimkit.config import get_config
from shimkit.core import CommandRunner, Platform, sudo_prefix


class OracleRemover:
    """macOS-only Oracle JDK cleanup."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    def available(self) -> bool:
        return self._platform.is_macos

    @property
    def patterns(self) -> list[str]:
        """Resolved glob patterns with ``~`` expanded for the current user."""
        return [
            str(Path(p).expanduser())
            for p in get_config().tools.java.oracle_glob_patterns
        ]

    @property
    def safe_roots(self) -> tuple[str, ...]:
        """Resolved safe-root prefixes — paths outside these are never deleted."""
        return tuple(
            str(Path(r).expanduser()) for r in get_config().tools.java.oracle_safe_roots
        )

    def remove(self) -> bool:
        """Delete every matched artifact. Returns True if anything was removed."""
        if not self.available():
            return False
        removed = False
        prefix = sudo_prefix()
        roots = self.safe_roots
        for pattern in self.patterns:
            for hit in glob.glob(pattern):
                p = Path(hit)
                if not p.exists():
                    continue
                if not any(str(p).startswith(r) for r in roots):
                    continue  # paranoia: never delete outside expected roots
                r = CommandRunner.run([*prefix, "rm", "-rf", str(p)])
                if r.ok:
                    removed = True
        return removed
