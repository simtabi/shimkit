"""Typed value objects for ``shimkit docker-clean``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DockerDisk:
    """Parsed ``docker system df --format json`` snapshot."""

    images_count: int = 0
    images_size_bytes: int = 0
    images_reclaimable_bytes: int = 0
    containers_count: int = 0
    containers_size_bytes: int = 0
    containers_reclaimable_bytes: int = 0
    volumes_count: int = 0
    volumes_size_bytes: int = 0
    volumes_reclaimable_bytes: int = 0
    build_cache_size_bytes: int = 0
    build_cache_reclaimable_bytes: int = 0


@dataclass
class CleanupPlan:
    """What ``docker-clean custom`` / ``docker-clean nuke`` will do."""

    containers: bool = False
    images: bool = False
    volumes: bool = False
    networks: bool = False
    build_cache: bool = False
    restart_daemon: bool = False

    @property
    def any_destructive(self) -> bool:
        return any(
            (self.containers, self.images, self.volumes, self.networks, self.build_cache)
        )


@dataclass
class CleanupOutcome:
    """Per-step outcome."""

    step: str
    applied: bool = False
    reclaimed_bytes: int = 0
    notes: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class BuildxBuilder:
    name: str
    driver: str = ""
    nodes: int = 0
