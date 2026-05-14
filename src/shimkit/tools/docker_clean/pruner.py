"""Prune operations — containers, images, volumes, networks, builders.

Uses the docker-py SDK where possible (typed results, exceptions over
exit codes). Builder cleanup iterates ``docker buildx ls`` and prunes
each builder so named buildx caches aren't missed — the bug that the
bash script had at line 632.
"""

from __future__ import annotations

from typing import Any

from shimkit.core import CommandRunner

from . import client
from .models import CleanupOutcome


def stop_all_containers(c: Any) -> CleanupOutcome:
    out = CleanupOutcome(step="stop_all_containers")
    running = c.containers.list(filters={"status": "running"})
    if not running:
        out.notes.append("No running containers.")
        return out
    for ctr in running:
        try:
            ctr.stop(timeout=10)
        except Exception as exc:
            out.notes.append(f"Could not stop {ctr.short_id}: {exc}")
    out.applied = True
    out.notes.append(f"Stopped {len(running)} container(s).")
    return out


def remove_all_containers(c: Any) -> CleanupOutcome:
    out = CleanupOutcome(step="remove_all_containers")
    ctrs = c.containers.list(all=True)
    if not ctrs:
        out.notes.append("No containers to remove.")
        return out
    removed = 0
    for ctr in ctrs:
        try:
            ctr.remove(force=True)
            removed += 1
        except Exception as exc:
            out.notes.append(f"Could not remove {ctr.short_id}: {exc}")
    out.applied = removed > 0
    out.notes.append(f"Removed {removed}/{len(ctrs)} container(s).")
    return out


def prune_images(c: Any, all_images: bool = False) -> CleanupOutcome:
    """`docker image prune` (dangling only) or `-a` for unused."""
    out = CleanupOutcome(step="prune_images")
    try:
        res = c.images.prune(filters={"dangling": False}) if all_images else c.images.prune()
    except Exception as exc:
        out.error = str(exc)
        return out
    out.applied = True
    out.reclaimed_bytes = int(res.get("SpaceReclaimed") or 0)
    out.notes.append(f"Reclaimed ~{out.reclaimed_bytes // (1024 * 1024)} MiB.")
    return out


def prune_volumes(c: Any) -> CleanupOutcome:
    out = CleanupOutcome(step="prune_volumes")
    try:
        res = c.volumes.prune()
    except Exception as exc:
        out.error = str(exc)
        return out
    out.applied = True
    out.reclaimed_bytes = int(res.get("SpaceReclaimed") or 0)
    return out


def prune_networks(c: Any) -> CleanupOutcome:
    out = CleanupOutcome(step="prune_networks")
    try:
        res = c.networks.prune()
    except Exception as exc:
        out.error = str(exc)
        return out
    out.applied = True
    deleted = res.get("NetworksDeleted") or []
    out.notes.append(f"Removed {len(deleted)} network(s).")
    return out


def prune_buildx_builders(*, all_caches: bool = True) -> CleanupOutcome:
    """Iterate `docker buildx ls` and prune each builder — fixes the
    bash script's bug of only touching the legacy local builder."""
    out = CleanupOutcome(step="prune_buildx_builders")
    builders = client.list_buildx_builders()
    if not builders:
        out.notes.append("No buildx builders found; falling back to `builder prune`.")
        # Legacy local builder.
        r = CommandRunner.run(["docker", "builder", "prune", "-af"])
        out.applied = r.ok
        return out
    for b in builders:
        cmd = ["docker", "buildx", "prune", "--builder", b.name, "--force"]
        if all_caches:
            cmd.append("--all")
        r = CommandRunner.run(cmd)
        if r.ok:
            out.notes.append(f"  pruned {b.name}")
        else:
            out.notes.append(f"  FAIL  {b.name}")
    out.applied = True
    return out


def orphans(c: Any) -> CleanupOutcome:
    """Remove dangling images + unused volumes only — narrower than system prune."""
    out = CleanupOutcome(step="orphans")
    img = prune_images(c, all_images=False)
    vol = prune_volumes(c)
    out.applied = img.applied or vol.applied
    out.reclaimed_bytes = img.reclaimed_bytes + vol.reclaimed_bytes
    out.notes.extend(img.notes + vol.notes)
    return out
