"""Typed value objects for ``shimkit adguard``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AdGuardInstall:
    """Detected AdGuard Home installation."""

    binary: Path
    yaml_path: Path | None
    install_root: Path


@dataclass(frozen=True)
class PortOwner:
    """A process holding a port."""

    pid: int
    name: str
    unit: str | None = None


@dataclass(frozen=True)
class PortConflict:
    """A port AGH needs that is held by something else."""

    port: int
    proto: Literal["tcp", "udp"]
    role: str
    owner: PortOwner


@dataclass
class FixOutcome:
    """Per-step outcome of `adguard fix`."""

    step: str
    applied: bool = False
    notes: list[str] = field(default_factory=list)
    error: str | None = None
