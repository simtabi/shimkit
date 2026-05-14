"""DockerCleanManager — orchestrator for ``shimkit docker-clean``."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from shimkit.config import get_config
from shimkit.core import (
    UI,
    CommandRunner,
    Event,
    Menu,
    Platform,
    Systemd,
    emit_json,
    get_logger,
)

from . import client, desktop, pruner, schedule
from .models import CleanupOutcome, DockerDisk

_LOG = get_logger("docker_clean")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77


def _require_optional_extras() -> bool:
    try:
        import docker  # noqa: F401
    except ImportError:
        UI.error(
            "shimkit docker-clean needs the docker SDK.\n"
            "  Install with:  uv tool install 'shimkit[docker-clean]'\n"
            "  or:            pipx inject shimkit docker"
        )
        return False
    return True


class DockerCleanManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None
        self._client: Any | None = None

    @classmethod
    def create(cls) -> DockerCleanManager:
        return cls()

    def boot(self, *, require_daemon: bool = True) -> DockerCleanManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(f"shimkit docker-clean: unsupported platform {self._platform.system}.")
            sys.exit(EX_UNAVAILABLE)
        if not _require_optional_extras():
            sys.exit(EX_UNAVAILABLE)
        self._client = client.get_client()
        if self._client is None and require_daemon:
            UI.error(
                "Docker daemon is not reachable. "
                "Start Docker Desktop or systemctl start docker, then retry."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ---- read-only --------------------------------------------------

    def status(self, *, json_out: bool = False) -> int:
        disk = client.disk_usage() or DockerDisk()
        desktop_status = desktop.status() if self._platform and self._platform.is_macos else "n/a"
        if json_out:
            emit_json(
                Event(
                    tool="docker_clean",
                    step="status",
                    status="ok",
                    data={
                        "desktop": desktop_status,
                        "wsl": client.is_wsl(),
                        "disk": {
                            "images": {
                                "count": disk.images_count,
                                "size": disk.images_size_bytes,
                                "reclaimable": disk.images_reclaimable_bytes,
                            },
                            "containers": {
                                "count": disk.containers_count,
                                "size": disk.containers_size_bytes,
                                "reclaimable": disk.containers_reclaimable_bytes,
                            },
                            "volumes": {
                                "count": disk.volumes_count,
                                "size": disk.volumes_size_bytes,
                                "reclaimable": disk.volumes_reclaimable_bytes,
                            },
                            "build_cache": {
                                "size": disk.build_cache_size_bytes,
                                "reclaimable": disk.build_cache_reclaimable_bytes,
                            },
                        },
                    },
                )
            )
            return EX_OK
        UI.header("Docker resource status")
        UI.line(f"  desktop : {desktop_status}")
        UI.line(f"  wsl     : {client.is_wsl()}")
        UI.line(
            f"  images  : {disk.images_count} "
            f"({_human(disk.images_size_bytes)}, reclaim {_human(disk.images_reclaimable_bytes)})"
        )
        UI.line(
            f"  containers : {disk.containers_count} "
            f"({_human(disk.containers_size_bytes)}, "
            f"reclaim {_human(disk.containers_reclaimable_bytes)})"
        )
        UI.line(
            f"  volumes : {disk.volumes_count} "
            f"({_human(disk.volumes_size_bytes)}, reclaim {_human(disk.volumes_reclaimable_bytes)})"
        )
        UI.line(
            f"  cache   : {_human(disk.build_cache_size_bytes)} "
            f"(reclaim {_human(disk.build_cache_reclaimable_bytes)})"
        )
        return EX_OK

    def inspect(self, kind: str, *, json_out: bool = False) -> int:
        c = self._client
        if c is None:
            UI.error("Docker daemon not reachable.")
            return EX_UNAVAILABLE
        kind = kind.lower()
        data: list[dict[str, Any]] = []
        try:
            if kind == "containers":
                data = [
                    {
                        "id": ctr.short_id,
                        "name": ctr.name,
                        "status": ctr.status,
                        "image": ctr.image.tags[0] if ctr.image.tags else ctr.image.short_id,
                    }
                    for ctr in c.containers.list(all=True)
                ]
            elif kind == "images":
                data = [
                    {"id": img.short_id, "tags": img.tags, "size": img.attrs.get("Size", 0)}
                    for img in c.images.list()
                ]
            elif kind == "volumes":
                data = [
                    {"name": vol.name, "mountpoint": vol.attrs.get("Mountpoint")}
                    for vol in c.volumes.list()
                ]
            elif kind == "networks":
                data = [
                    {"id": net.short_id, "name": net.name, "driver": net.attrs.get("Driver")}
                    for net in c.networks.list()
                ]
            elif kind == "cache":
                # buildx cache breakdown via SDK isn't exposed; fall back to text.
                r = CommandRunner.run(["docker", "buildx", "du"])
                if json_out:
                    data = [{"raw": r.stdout}]
                else:
                    UI.line(r.stdout)
                    return EX_OK
            else:
                UI.error(f"Unknown inspect kind: {kind}")
                return EX_FAIL
        except Exception as exc:
            UI.error(str(exc))
            return EX_FAIL

        if json_out:
            emit_json(
                Event(
                    tool="docker_clean", step=f"inspect:{kind}", status="ok", data={"items": data}
                )
            )
        else:
            UI.header(f"Inspect: {kind}")
            for item in data:
                UI.line(f"  {item}")
        return EX_OK

    # ---- mutating ----------------------------------------------------

    def stop_all(self, *, dry_run: bool = False) -> int:
        if dry_run:
            UI.info("[dry-run] Would stop all running containers.")
            return EX_OK
        if self._client is None:
            UI.error("Docker daemon not reachable.")
            return EX_UNAVAILABLE
        out = pruner.stop_all_containers(self._client)
        return self._emit_one(out)

    def prune(self, kind: str, *, dry_run: bool = False) -> int:
        if dry_run:
            UI.info(f"[dry-run] Would prune {kind}.")
            return EX_OK
        if self._client is None:
            UI.error("Docker daemon not reachable.")
            return EX_UNAVAILABLE
        if kind == "images":
            out = pruner.prune_images(self._client, all_images=True)
        elif kind == "volumes":
            out = pruner.prune_volumes(self._client)
        elif kind == "networks":
            out = pruner.prune_networks(self._client)
        elif kind == "builders":
            out = pruner.prune_buildx_builders(
                all_caches=get_config().tools.docker_clean.default_buildx_prune_all
            )
        elif kind == "orphans":
            out = pruner.orphans(self._client)
        else:
            UI.error(f"Unknown prune kind: {kind}")
            return EX_FAIL
        return self._emit_one(out)

    def quick(self, *, dry_run: bool = False, json_out: bool = False) -> int:
        outcomes: list[CleanupOutcome] = []
        if dry_run:
            UI.info("[dry-run] Would stop containers + prune images + volumes + networks.")
            return EX_OK
        if self._client is None:
            return EX_UNAVAILABLE
        outcomes.append(pruner.stop_all_containers(self._client))
        outcomes.append(pruner.remove_all_containers(self._client))
        outcomes.append(pruner.prune_images(self._client, all_images=True))
        outcomes.append(pruner.prune_volumes(self._client))
        outcomes.append(pruner.prune_networks(self._client))
        return self._emit_many(outcomes, json_out=json_out)

    def nuke(self, *, confirm: str | None, json_out: bool = False) -> int:
        token = get_config().tools.docker_clean.nuke_confirm_token
        if confirm != token:
            UI.error(f"Severe action. Pass --confirm {token} to proceed.")
            return EX_FAIL
        if self._client is None:
            return EX_UNAVAILABLE
        outcomes: list[CleanupOutcome] = []
        outcomes.append(pruner.stop_all_containers(self._client))
        outcomes.append(pruner.remove_all_containers(self._client))
        outcomes.append(pruner.prune_images(self._client, all_images=True))
        outcomes.append(pruner.prune_volumes(self._client))
        outcomes.append(pruner.prune_networks(self._client))
        outcomes.append(
            pruner.prune_buildx_builders(
                all_caches=get_config().tools.docker_clean.default_buildx_prune_all
            )
        )
        return self._emit_many(outcomes, json_out=json_out)

    def restart(self) -> int:
        if self._platform is None:
            return EX_UNAVAILABLE
        if self._platform.is_macos:
            if desktop.restart(self._platform):
                # Verify the daemon comes back, with a real loop (the bash
                # version had ((attempt++)) trip set -e so it ran once).
                timeout = get_config().tools.docker_clean.daemon_verify_timeout_seconds
                for _ in range(timeout):
                    if client.get_client() is not None:
                        UI.success("Docker daemon back online.")
                        return EX_OK
                    time.sleep(1)
                UI.error("Docker daemon did not come back within timeout.")
                return EX_FAIL
            UI.error("Failed to restart Docker Desktop.")
            return EX_FAIL
        if self._platform.is_linux:
            r = Systemd.restart("docker")
            return EX_OK if r.ok else EX_NOPERM
        return EX_UNAVAILABLE

    def compose_down(self, path: Path, *, with_volumes: bool = False) -> int:
        cmd = ["docker", "compose", "-f", str(path), "down"]
        if with_volumes:
            cmd.append("-v")
        r = CommandRunner.run(cmd, capture_output=False)
        return EX_OK if r.ok else EX_FAIL

    def schedule_emit(self, interval: str, out: Path | None) -> int:
        body = schedule.emit(interval, self._platform)
        if out:
            out.write_text(body, encoding="utf-8")
            UI.success(f"Wrote scheduling snippet to {out}")
        else:
            UI.line(body)
        return EX_OK

    # ---- helpers -----------------------------------------------------

    def _emit_one(self, outcome: CleanupOutcome) -> int:
        if outcome.error:
            UI.error(f"{outcome.step}: {outcome.error}")
            return EX_FAIL
        if outcome.applied:
            UI.success(outcome.step)
        else:
            UI.warning(outcome.step)
        for n in outcome.notes:
            UI.dim(f"  {n}")
        return EX_OK

    def _emit_many(self, outcomes: list[CleanupOutcome], *, json_out: bool) -> int:
        if json_out:
            emit_json(
                [
                    Event(
                        tool="docker_clean",
                        step=o.step,
                        status="error" if o.error else ("ok" if o.applied else "warning"),
                        message=o.error or "",
                        data={"reclaimed_bytes": o.reclaimed_bytes, "notes": o.notes},
                    )
                    for o in outcomes
                ]
            )
            return EX_OK if not any(o.error for o in outcomes) else EX_FAIL
        for o in outcomes:
            self._emit_one(o)
        return EX_OK if not any(o.error for o in outcomes) else EX_FAIL

    # ---- interactive menu --------------------------------------------

    def run(self) -> None:
        actions: list[tuple[str, Callable[[], object]]] = [
            ("Status (disk usage)", lambda: self.status()),
            ("Quick cleanup", lambda: self.quick()),
            ("Prune images", lambda: self.prune("images")),
            ("Prune volumes", lambda: self.prune("volumes")),
            ("Prune networks", lambda: self.prune("networks")),
            ("Prune buildx caches", lambda: self.prune("builders")),
            ("Stop all containers", lambda: self.stop_all()),
            ("Exit", lambda: None),
        ]
        labels = [lbl for lbl, _ in actions]
        dispatch = dict(actions)
        while True:
            choice = Menu.select("Docker cleanup — what would you like to do?", labels)
            if choice is None or choice == "Exit":
                UI.info("Goodbye!")
                return
            handler = dispatch.get(choice)
            if handler:
                handler()


def _human(n: int) -> str:
    """Pretty-print a byte count."""
    size: float = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024:
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PiB"
