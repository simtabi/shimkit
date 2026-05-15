"""Typed value objects for ``shimkit env``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EnvEntry:
    """One ``KEY=value`` line from a .env file."""

    key: str
    value: str
    quoted: bool = False  # was the value double-quoted in the source?
    comment: str | None = None  # trailing "# foo" text


@dataclass
class EnvFile:
    """Parsed view of a .env file. Order preserved for round-trip."""

    path: Path | None = None
    # Mixed list: each item is either an EnvEntry or a raw string
    # (blank line, comment-only line) so round-trip preserves layout.
    items: list[EnvEntry | str] = field(default_factory=list)

    def entries(self) -> list[EnvEntry]:
        return [it for it in self.items if isinstance(it, EnvEntry)]

    def find(self, key: str) -> EnvEntry | None:
        for e in self.entries():
            if e.key == key:
                return e
        return None

    def keys(self) -> list[str]:
        return [e.key for e in self.entries()]
