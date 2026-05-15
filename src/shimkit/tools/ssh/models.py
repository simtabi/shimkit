"""Typed value objects for ``shimkit ssh``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KeyEntry:
    """One ``id_<type>[.pub]`` key pair sitting in ``~/.ssh``."""

    private: Path
    public: Path | None  # may be absent if the .pub file was deleted
    key_type: str  # "ed25519", "rsa", "ecdsa", "dsa", "?"
    fingerprint: str | None = None
    comment: str | None = None

    @property
    def name(self) -> str:
        return self.private.name


@dataclass(frozen=True)
class AgentKey:
    """One key loaded into ``ssh-agent`` per ``ssh-add -L``."""

    key_type: str
    fingerprint: str
    comment: str | None = None


@dataclass(frozen=True)
class PermIssue:
    """One file/dir whose mode is too permissive."""

    path: Path
    actual: str  # octal mode, three digits, e.g. "644"
    expected: str

    @property
    def kind(self) -> str:
        if self.path.is_dir():
            return "dir"
        if self.path.suffix == ".pub":
            return "public_key"
        return "private_key_or_known_file"
