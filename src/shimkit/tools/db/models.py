"""Typed value objects for ``shimkit db``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpResult:
    """Outcome of one ``db <engine> up`` invocation."""

    engine: str
    container_name: str
    image: str
    host_port: int
    container_port: int
    bind_host: str
    # "created" → fresh container; "started" → existed-stopped, now
    # running; "already_running" → no-op.
    action: str
    volume_path: str | None


@dataclass(frozen=True)
class StatusRow:
    """One row of ``db <engine> status`` / ``db ls`` output."""

    container_name: str
    engine: str
    image: str
    state: str  # "running" / "exited" / "missing"
    host_port: int | None
    container_port: int | None
    bind_host: str | None
    volume_path: str | None
