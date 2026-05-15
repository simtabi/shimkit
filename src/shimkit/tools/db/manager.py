"""DbManager — orchestrator for ``shimkit db``.

Composes :class:`~shimkit.core.docker.DockerEnv` (Rule 2 chokepoint
for SDK calls) with the per-engine drivers in
:mod:`shimkit.tools.db.engines`. Each subcommand is a single method
on the manager.

``--on-host`` routes through :class:`~shimkit.core.HostService`
(systemd on Linux, brew services on macOS) instead of DockerEnv,
managing an already-installed host engine rather than a container.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from shimkit.config import get_config
from shimkit.core import (
    UI,
    CommandRunner,
    DockerEnv,
    Event,
    HostService,
    Platform,
    emit_json,
    get_logger,
)
from shimkit.core import version as _vc

from . import engines as _engines
from .engines.base import Engine, UnsupportedEngineOperationError
from .models import StatusRow, UpResult

_LOG = get_logger("db")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
SCOPE = "db"


class DbManager:
    """Container-first database orchestration. Builder pattern:
    ``DbManager.create().boot().for_engine("mysql").up(...)``.
    """

    def __init__(self) -> None:
        self._env: DockerEnv | None = None

    @classmethod
    def create(cls) -> DbManager:
        return cls()

    def boot(self, *, force: bool = False, on_host: bool = False) -> DbManager:
        """Verify dependencies. Default path preflights docker + the
        daemon; ``on_host=True`` skips docker entirely (the caller is
        managing host services, not containers).
        """
        if on_host:
            return self
        try:
            _vc.preflight(("docker",), force=force)
        except _vc.VersionViolationError as exc:
            for r in exc.results:
                if r.status is _vc.Status.MISSING:
                    UI.error("`docker` is not on PATH.")
                elif r.status is _vc.Status.OUT_OF_RANGE and r.tool_version:
                    UI.error(
                        f"docker {r.tool_version.raw} is out of range — "
                        f"shimkit db requires {r.constraint.min or '<any>'}+."
                    )
                if r.remediation:
                    UI.dim(f"  → {r.remediation}")
            sys.exit(EX_UNAVAILABLE)
        self._env = DockerEnv.create().boot()
        return self

    # ─── engine accessor ─────────────────────────────────────────────

    def for_engine(self, name: str) -> _EngineBound:
        engine = _engines.get(name)
        if engine is None:
            UI.error(f"Unknown engine: {name!r}. Known: {', '.join(_engines.REGISTRY)}.")
            sys.exit(EX_FAIL)
        cfg = get_config().tools.db.engines.get(name)
        if cfg is None:
            UI.error(f"Engine {name!r} is registered but missing config entry.")
            sys.exit(EX_FAIL)
        # `env` is None when boot() was called with on_host=True. The
        # container-mode methods assert env is not None; --on-host
        # methods don't touch it.
        return _EngineBound(
            env=self._env, engine=engine, image=cfg.image, default_port=cfg.default_port
        )

    # ─── ls (across engines) ────────────────────────────────────────

    def ls(self, *, json_out: bool = False) -> int:
        assert self._env is not None
        containers = self._env.list_managed(scope=SCOPE)
        rows: list[StatusRow] = [_to_status_row(c) for c in containers]
        if json_out:
            emit_json(
                Event(
                    tool="db",
                    step="ls",
                    status="ok",
                    data={
                        "containers": [
                            {
                                "container_name": r.container_name,
                                "engine": r.engine,
                                "image": r.image,
                                "state": r.state,
                                "host_port": r.host_port,
                                "container_port": r.container_port,
                                "bind_host": r.bind_host,
                                "volume_path": r.volume_path,
                            }
                            for r in rows
                        ]
                    },
                )
            )
            return EX_OK
        if not rows:
            UI.info("No shimkit-managed db containers.")
            return EX_OK
        UI.header(f"shimkit db ({len(rows)})")
        for r in rows:
            host = f"{r.bind_host}:{r.host_port}" if r.host_port is not None else "<no port>"
            UI.line(f"  {r.engine:11s} {r.state:8s} {host}  {r.container_name}")
        return EX_OK


class _EngineBound:
    """A DbManager + one engine + its config. Holds the per-engine
    operations (``up`` / ``down`` / ``shell`` / etc.) so the command
    layer can fluent-chain them.
    """

    def __init__(
        self,
        *,
        env: DockerEnv | None,
        engine: Engine,
        image: str,
        default_port: int,
    ) -> None:
        # `env` is None in --on-host mode; the container-mode methods
        # assert env-not-None on entry.
        self._env = env
        self._engine = engine
        self._image = image
        self._default_port = default_port

    # ─── up ──────────────────────────────────────────────────────────

    def up(
        self,
        *,
        id_: str | None = None,
        host_port: int | None = None,
        bind_host: str | None = None,
        volume: Path | None = None,
        ephemeral: bool = False,
        password: str | None = None,
        link_host: str | None = None,
        link_port: int | None = None,
        json_out: bool = False,
        dry_run: bool = False,
    ) -> int:
        assert self._env is not None, "container-mode methods require boot() without on_host=True"
        cfg = get_config().tools.db
        id_ = id_ or cfg.default_id
        port = host_port or self._default_port
        bind = bind_host or cfg.default_bind_host
        pwd = password or cfg.default_password
        name = DockerEnv.container_name(SCOPE, self._engine.name, id_)

        if ephemeral:
            volume_path: str | None = None
        else:
            v = volume or (
                Path(cfg.default_volume_root).expanduser() / f"{self._engine.name}-{id_}"
            )
            volume_path = str(v)

        extras: dict[str, str] = {}
        if self._engine.requires_link() or self._engine.name == "phpmyadmin":
            if link_host:
                extras["link_host"] = link_host
            if link_port:
                extras["link_port"] = str(link_port)

        env = self._engine.environment_for_up(password=pwd, extras=extras)
        volumes = self._engine.volume_mounts(volume_root=volume_path)
        ports = {f"{self._engine.container_port}/tcp": (bind, port)}
        extra_hosts = (
            {"host.docker.internal": "host-gateway"}
            if self._engine.requires_link() or self._engine.name == "phpmyadmin"
            else {}
        )

        existing = self._env.find(name)
        if existing is not None:
            state = getattr(existing, "status", None)
            if state == "running":
                result = UpResult(
                    engine=self._engine.name,
                    container_name=name,
                    image=self._image,
                    host_port=port,
                    container_port=self._engine.container_port,
                    bind_host=bind,
                    action="already_running",
                    volume_path=volume_path,
                )
            else:
                if dry_run:
                    UI.info(f"--dry-run: would start existing container {name}.")
                    return EX_OK
                self._env.start(name)
                result = UpResult(
                    engine=self._engine.name,
                    container_name=name,
                    image=self._image,
                    host_port=port,
                    container_port=self._engine.container_port,
                    bind_host=bind,
                    action="started",
                    volume_path=volume_path,
                )
        else:
            if dry_run:
                UI.info(f"--dry-run: would run `docker run -d --name {name}` from {self._image}.")
                return EX_OK
            if volume_path:
                Path(volume_path).mkdir(parents=True, exist_ok=True)
            self._env.run(
                self._image,
                name=name,
                env=env,
                ports=ports,
                volumes=volumes,
                extra_hosts=extra_hosts or None,
                restart_policy={"Name": "unless-stopped"},
            )
            result = UpResult(
                engine=self._engine.name,
                container_name=name,
                image=self._image,
                host_port=port,
                container_port=self._engine.container_port,
                bind_host=bind,
                action="created",
                volume_path=volume_path,
            )
        return self._emit_up_result(result, json_out=json_out)

    # ─── down ────────────────────────────────────────────────────────

    def down(self, *, id_: str | None = None, json_out: bool = False, dry_run: bool = False) -> int:
        assert self._env is not None, "container-mode methods require boot() without on_host=True"
        cfg = get_config().tools.db
        id_ = id_ or cfg.default_id
        name = DockerEnv.container_name(SCOPE, self._engine.name, id_)
        if dry_run:
            UI.info(f"--dry-run: would stop and remove {name}.")
            return EX_OK
        stopped = self._env.stop(name)
        removed = self._env.remove(name)
        action = "removed" if removed else ("missing" if not stopped else "stopped")
        if json_out:
            emit_json(
                Event(
                    tool="db",
                    step="down",
                    status="ok",
                    data={"engine": self._engine.name, "container_name": name, "action": action},
                )
            )
            return EX_OK
        if action == "missing":
            UI.info(f"{name} was not running; nothing to remove.")
        else:
            UI.success(f"Removed {name}.")
        return EX_OK

    # ─── shell ───────────────────────────────────────────────────────

    def shell(self, *, id_: str | None = None, password: str | None = None) -> int:
        assert self._env is not None, "container-mode methods require boot() without on_host=True"
        cfg = get_config().tools.db
        id_ = id_ or cfg.default_id
        name = DockerEnv.container_name(SCOPE, self._engine.name, id_)
        if not self._engine.supports_shell():
            UI.error(f"Engine {self._engine.name!r} does not have a shell.")
            return EX_FAIL
        existing = self._env.find(name)
        if existing is None:
            UI.error(f"{name} is not running. Try `shimkit db {self._engine.name} up` first.")
            return EX_FAIL
        try:
            argv = self._engine.shell_argv(password=password or cfg.default_password)
        except UnsupportedEngineOperationError as exc:
            UI.error(str(exc))
            return EX_FAIL
        # shell is interactive; we emit the argv via UI and let the
        # user `docker exec -it ...` themselves OR (when capture_output
        # is False) the SDK's exec_run streams. For Phase 6 simplicity
        # we shell out via CommandRunner so the user gets a TTY.
        from shimkit.core import CommandRunner

        cmd = ["docker", "exec", "-it", name, *argv]
        # Forward env for psql which reads PGPASSWORD.
        if self._engine.name == "postgres":
            cmd = [
                "docker",
                "exec",
                "-it",
                "-e",
                f"PGPASSWORD={password or cfg.default_password}",
                name,
                *argv,
            ]
        r = CommandRunner.run(cmd, capture_output=False)
        return EX_OK if r.ok else EX_FAIL

    # ─── dump ────────────────────────────────────────────────────────

    def dump(
        self,
        *,
        id_: str | None = None,
        password: str | None = None,
        out: Path | None = None,
        json_out: bool = False,
    ) -> int:
        assert self._env is not None, "container-mode methods require boot() without on_host=True"
        cfg = get_config().tools.db
        id_ = id_ or cfg.default_id
        name = DockerEnv.container_name(SCOPE, self._engine.name, id_)
        if not self._engine.supports_dump():
            UI.error(f"Engine {self._engine.name!r} does not support `dump`.")
            return EX_FAIL
        existing = self._env.find(name)
        if existing is None:
            UI.error(f"{name} is not running.")
            return EX_FAIL
        try:
            argv = self._engine.dump_argv(password=password or cfg.default_password)
        except UnsupportedEngineOperationError as exc:
            UI.error(str(exc))
            return EX_FAIL
        env_extra = (
            {"PGPASSWORD": password or cfg.default_password}
            if self._engine.name == "postgres"
            else None
        )
        outcome = self._env.exec(name, argv, environment=env_extra)
        if not outcome.ok:
            UI.error(f"dump failed (exit {outcome.exit_code}): {outcome.stderr.strip()}")
            return EX_FAIL
        if out is None:
            UI.line(outcome.stdout)
        else:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(outcome.stdout, encoding="utf-8")
            except OSError as exc:
                UI.error(f"Could not write {out}: {exc}")
                return EX_FAIL
            if json_out:
                emit_json(
                    Event(
                        tool="db",
                        step="dump",
                        status="ok",
                        data={
                            "engine": self._engine.name,
                            "container_name": name,
                            "out": str(out),
                            "bytes": len(outcome.stdout),
                        },
                    )
                )
            else:
                UI.success(f"Wrote dump to {out} ({len(outcome.stdout)} bytes).")
        return EX_OK

    # ─── reset (SEVERE) ──────────────────────────────────────────────

    def reset(self, *, id_: str | None = None, dry_run: bool = False) -> int:
        """Stop + remove the container AND its persistent volume.
        Caller already validated the SEVERE token at the command layer.
        """
        assert self._env is not None, "container-mode methods require boot() without on_host=True"
        cfg = get_config().tools.db
        id_ = id_ or cfg.default_id
        name = DockerEnv.container_name(SCOPE, self._engine.name, id_)
        volume = Path(cfg.default_volume_root).expanduser() / f"{self._engine.name}-{id_}"
        if dry_run:
            UI.info(f"--dry-run: would remove container {name} AND volume {volume}.")
            return EX_OK
        self._env.stop(name)
        self._env.remove(name, force=True)
        deleted = self._env.remove_volume(volume)
        UI.success(
            f"Reset {self._engine.name}/{id_}: container removed; volume {'deleted' if deleted else '(was absent)'}."
        )
        return EX_OK

    # ─── status ──────────────────────────────────────────────────────

    def status(self, *, id_: str | None = None, json_out: bool = False) -> int:
        assert self._env is not None, "container-mode methods require boot() without on_host=True"
        cfg = get_config().tools.db
        id_ = id_ or cfg.default_id
        name = DockerEnv.container_name(SCOPE, self._engine.name, id_)
        existing = self._env.find(name)
        if existing is None:
            row = StatusRow(
                container_name=name,
                engine=self._engine.name,
                image=self._image,
                state="missing",
                host_port=None,
                container_port=None,
                bind_host=None,
                volume_path=None,
            )
        else:
            row = _to_status_row(existing, fallback_engine=self._engine.name)
        if json_out:
            emit_json(
                Event(
                    tool="db",
                    step="status",
                    status="ok" if row.state == "running" else "warning",
                    data={
                        "container_name": row.container_name,
                        "engine": row.engine,
                        "image": row.image,
                        "state": row.state,
                        "host_port": row.host_port,
                        "container_port": row.container_port,
                        "bind_host": row.bind_host,
                        "volume_path": row.volume_path,
                    },
                )
            )
            return EX_OK
        UI.header(f"{row.container_name} — {row.state}")
        UI.line(f"  engine     {row.engine}")
        UI.line(f"  image      {row.image}")
        if row.host_port is not None:
            UI.line(f"  port       {row.bind_host}:{row.host_port} → :{row.container_port}")
        if row.volume_path:
            UI.line(f"  volume     {row.volume_path}")
        return EX_OK

    # ─── --on-host ───────────────────────────────────────────────────

    def up_on_host(self, *, json_out: bool = False, dry_run: bool = False) -> int:
        """Start the host-installed service for this engine."""
        svc = self._on_host_preflight()
        if svc is None:
            return EX_FAIL
        service_name, host = svc
        if dry_run:
            UI.info(f"--dry-run: would start host service {service_name!r}.")
            return EX_OK
        result = host.start(service_name)
        return self._emit_host_result(
            result, step="up", service=service_name, json_out=json_out
        )

    def down_on_host(self, *, json_out: bool = False, dry_run: bool = False) -> int:
        """Stop the host-installed service for this engine."""
        svc = self._on_host_preflight()
        if svc is None:
            return EX_FAIL
        service_name, host = svc
        if dry_run:
            UI.info(f"--dry-run: would stop host service {service_name!r}.")
            return EX_OK
        result = host.stop(service_name)
        return self._emit_host_result(
            result, step="down", service=service_name, json_out=json_out
        )

    def status_on_host(self, *, json_out: bool = False) -> int:
        """Report state of the host-installed service."""
        svc = self._on_host_preflight(quiet_missing_binary=True)
        if svc is None:
            return EX_FAIL
        service_name, host = svc
        state = host.state(service_name)
        if json_out:
            emit_json(
                Event(
                    tool="db",
                    step="status",
                    status="ok" if state == "running" else "warning",
                    data={
                        "engine": self._engine.name,
                        "mode": "on-host",
                        "service": service_name,
                        "state": state,
                    },
                )
            )
            return EX_OK
        UI.header(f"{self._engine.name} (on-host) — {state}")
        UI.line(f"  service    {service_name}")
        UI.line(f"  client     {self._engine.host_client_binary()}")
        return EX_OK

    def shell_on_host(self, *, password: str | None = None) -> int:
        """Connect to the host-installed engine via its CLI."""
        if not self._engine.supports_on_host():
            UI.error(f"Engine {self._engine.name!r} does not support --on-host.")
            return EX_FAIL
        cfg = get_config().tools.db
        client = self._engine.host_client_binary()
        if shutil.which(client) is None:
            UI.error(
                f"`{client}` is not on PATH. Install it via your package "
                "manager, or use the container shell (drop --on-host)."
            )
            return EX_UNAVAILABLE
        try:
            argv = self._engine.host_shell_argv(password=password or cfg.default_password)
        except UnsupportedEngineOperationError as exc:
            UI.error(str(exc))
            return EX_FAIL
        # Postgres reads PGPASSWORD from env; pass it through.
        env_extra: dict[str, str] | None = None
        if self._engine.name == "postgres" and (password or cfg.default_password):
            env_extra = {**os.environ, "PGPASSWORD": password or cfg.default_password}
        r = CommandRunner.run(argv, capture_output=False, env=env_extra)
        return EX_OK if r.ok else EX_FAIL

    # ─── --on-host internals ─────────────────────────────────────────

    def _on_host_preflight(
        self, *, quiet_missing_binary: bool = False
    ) -> tuple[str, HostService] | None:
        """Common gating for every --on-host method.

        Returns ``(service_name, host)`` on success; emits the
        relevant UI error and returns ``None`` on failure. The
        ``quiet_missing_binary`` flag lets `status` query a service
        even when the engine binary isn't on PATH (the service file
        may still exist and report stopped/missing usefully).
        """
        if not self._engine.supports_on_host():
            UI.error(
                f"Engine {self._engine.name!r} has no --on-host mode. "
                "Supported on-host engines: mysql, mariadb, postgres."
            )
            return None
        platform = Platform.detect()
        host = HostService.detect(platform)
        if host is None:
            UI.error(
                f"--on-host requires macOS or Linux; detected: {platform.system}."
            )
            return None
        cfg = get_config().tools.db
        entry = cfg.host_services.get(self._engine.name)
        if entry is None:
            UI.error(
                f"No host_services entry for {self._engine.name!r} in config."
            )
            return None
        service_name = entry.service_linux if platform.is_linux else entry.service_macos
        client = self._engine.host_client_binary()
        if not quiet_missing_binary and shutil.which(client) is None:
            UI.error(
                f"`{client}` is not on PATH. shimkit --on-host manages an "
                f"already-installed {self._engine.name}; install it via "
                "your package manager first (apt/brew/dnf)."
            )
            return None
        return service_name, host

    def _emit_host_result(
        self,
        result: Any,
        *,
        step: str,
        service: str,
        json_out: bool,
    ) -> int:
        if json_out:
            emit_json(
                Event(
                    tool="db",
                    step=step,
                    status="ok" if result.ok else "error",
                    data={
                        "engine": self._engine.name,
                        "mode": "on-host",
                        "service": service,
                        "state": result.state,
                        "stderr": result.stderr,
                    },
                )
            )
            return EX_OK if result.ok else EX_FAIL
        if not result.ok:
            UI.error(
                f"{step} failed on host service {service!r}: "
                f"{result.stderr.strip() or 'no detail'}"
            )
            return EX_FAIL
        UI.success(f"{step} host service {service} ({result.state}).")
        return EX_OK

    # ─── internal ────────────────────────────────────────────────────

    def _emit_up_result(self, result: UpResult, *, json_out: bool) -> int:
        if json_out:
            emit_json(
                Event(
                    tool="db",
                    step="up",
                    status="ok",
                    data={
                        "engine": result.engine,
                        "container_name": result.container_name,
                        "image": result.image,
                        "host_port": result.host_port,
                        "container_port": result.container_port,
                        "bind_host": result.bind_host,
                        "action": result.action,
                        "volume_path": result.volume_path,
                    },
                )
            )
            return EX_OK
        if result.action == "already_running":
            UI.info(f"{result.container_name} is already running.")
            return EX_OK
        verb = "started" if result.action == "started" else "started fresh"
        UI.success(
            f"{result.engine} {verb} → {result.bind_host}:{result.host_port} ({result.container_name})"
        )
        if result.volume_path:
            UI.dim(f"  data: {result.volume_path}")
        return EX_OK


# ─── module-level helpers ──────────────────────────────────────────────


def _to_status_row(container: Any, *, fallback_engine: str = "?") -> StatusRow:
    """Map a docker-py Container object onto a :class:`StatusRow`."""
    name = container.name
    image_attrs = getattr(container, "image", None)
    image = ""
    if image_attrs is not None:
        tags = getattr(image_attrs, "tags", None) or []
        image = tags[0] if tags else ""
    # Engine: parse from `shimkit-db-<engine>-<id>` or fall back.
    parts = name.split("-")
    engine = parts[2] if len(parts) >= 4 and parts[0] == "shimkit" else fallback_engine
    state = getattr(container, "status", "unknown") or "unknown"
    host_port: int | None = None
    container_port: int | None = None
    bind_host: str | None = None
    # ports = {"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "13306"}], ...}
    try:
        ports = getattr(container, "ports", {}) or {}
        for cport_str, bindings in ports.items():
            if not bindings:
                continue
            first = bindings[0]
            host_port = int(first.get("HostPort"))
            # Fallback when docker-py returns no HostIp on a wildcard
            # bind — we're reading parsed inspect output, not binding.
            bind_host = first.get("HostIp") or "0.0.0.0"  # nosec B104 — parser fallback, not a bind
            container_port = int(cport_str.split("/")[0])
            break
    except (KeyError, ValueError, TypeError):
        pass
    # Volume path comes from labels (we set "shimkit.volume" at run time)
    # but for v1 we don't capture it back; leave None.
    return StatusRow(
        container_name=name,
        engine=engine,
        image=image,
        state=state,
        host_port=host_port,
        container_port=container_port,
        bind_host=bind_host,
        volume_path=None,
    )
