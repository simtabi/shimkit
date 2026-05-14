"""Lazy docker-py client + ``docker system df --format json`` parsing.

Daemon operations go through the SDK. Things the SDK doesn't expose
(``docker desktop *``, ``docker compose``, ``docker buildx``) shell out
via :class:`CommandRunner` — still the single chokepoint.
"""

from __future__ import annotations

import json
import os
from typing import Any

from shimkit.core import CommandRunner

from .models import BuildxBuilder, DockerDisk


def get_client() -> Any | None:
    """Return a docker-py client, or None when the extra/daemon is unavailable."""
    try:
        import docker
    except ImportError:
        return None
    try:
        client = docker.from_env(timeout=10)
        # Cheap ping to verify the daemon is up.
        client.ping()
        return client
    except Exception:
        return None


def disk_usage() -> DockerDisk | None:
    """Run ``docker system df --format json`` and parse it."""
    r = CommandRunner.run(["docker", "system", "df", "--format", "json"])
    if not r.ok:
        return None
    # The output is one JSON object per row (NDJSON-ish on older docker)
    # or a top-level array. Try both.
    text = r.stdout.strip()
    if not text:
        return None
    try:
        if text.startswith("["):
            rows = json.loads(text)
        else:
            rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    except json.JSONDecodeError:
        return None

    out = DockerDisk()
    for row in rows:
        kind = (row.get("Type") or "").lower()
        size = _parse_size(row.get("Size") or row.get("TotalCount", "0"))
        reclaim = _parse_size(row.get("Reclaimable") or "0")
        count = _safe_int(row.get("Count") or row.get("TotalCount") or 0)
        if kind == "images":
            out = _replace(out, images_count=count, images_size_bytes=size,
                          images_reclaimable_bytes=reclaim)
        elif "container" in kind:
            out = _replace(out, containers_count=count, containers_size_bytes=size,
                          containers_reclaimable_bytes=reclaim)
        elif "volume" in kind:
            out = _replace(out, volumes_count=count, volumes_size_bytes=size,
                          volumes_reclaimable_bytes=reclaim)
        elif "build" in kind or "cache" in kind:
            out = _replace(out, build_cache_size_bytes=size,
                          build_cache_reclaimable_bytes=reclaim)
    return out


def list_buildx_builders() -> list[BuildxBuilder]:
    r = CommandRunner.run(["docker", "buildx", "ls", "--format", "json"])
    if not r.ok:
        return []
    builders: list[BuildxBuilder] = []
    for ln in r.stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        name = row.get("Name") or row.get("name")
        if not name:
            continue
        builders.append(
            BuildxBuilder(
                name=str(name),
                driver=str(row.get("Driver") or row.get("driver") or ""),
                nodes=len(row.get("Nodes") or row.get("nodes") or []),
            )
        )
    return builders


def is_wsl() -> bool:
    """Detect WSL: WSL_DISTRO_NAME env first, then /proc/version."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _parse_size(value: object) -> int:
    """Parse ``"1.234GB"`` / ``"12 MB"`` / ``42`` into bytes (approximate)."""
    if isinstance(value, int | float):
        return int(value)
    s = str(value).strip()
    if not s:
        return 0
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in sorted(units.items(), key=lambda kv: -len(kv[0])):
        if s.upper().endswith(suffix):
            try:
                return int(float(s[: -len(suffix)].strip()) * mult)
            except ValueError:
                return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _safe_int(v: object) -> int:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int | float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return 0
    return 0


def _replace(disk: DockerDisk, **kwargs: int) -> DockerDisk:
    from dataclasses import asdict, replace

    return replace(disk, **{k: v for k, v in kwargs.items() if k in asdict(disk)})
