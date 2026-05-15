"""DockerEnv -- shimkit's single chokepoint for the docker-py SDK.

Tools that need to drive containers (`shimkit db`, `shimkit stack`,
and eventually `shimkit docker-clean` when it migrates) go through
this class. The chokepoint pattern lets us:

- Boot-check the daemon once, fail fast with EX_UNAVAILABLE when
  it's not reachable.
- Standardise container + volume naming so every shimkit-managed
  container is identifiable (`shimkit-<scope>-<kind>-<id>`).
- Keep the `docker` package optional — it's installed via the
  ``[docker-clean]`` extra; importing on demand keeps shimkit's
  base install lean.

Tests mock at the ``shimkit.core.docker._from_env`` boundary; no
real daemon access happens in any test path.

Examples
--------

>>> from shimkit.core import DockerEnv
>>> env = DockerEnv.create().boot()                # doctest: +SKIP
>>> existing = env.find("shimkit-db-mysql-dev")     # doctest: +SKIP
>>> if existing is None:                            # doctest: +SKIP
...     env.run("mysql:8.0",
...             name="shimkit-db-mysql-dev",
...             env={"MYSQL_ROOT_PASSWORD": "..."},
...             ports={"3306/tcp": 13306})
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .ui import UI

if TYPE_CHECKING:
    pass  # docker types are dynamic; we keep them untyped at the boundary.

__all__ = [
    "DockerEnv",
    "DockerNotAvailableError",
    "ExecOutcome",
]

EX_UNAVAILABLE = 69
EX_NOPERM = 77


class DockerNotAvailableError(RuntimeError):
    """Raised when the docker-py SDK isn't installed (or the daemon
    isn't reachable). Callers usually map this to ``sys.exit(69)``.
    """


@dataclass(frozen=True)
class ExecOutcome:
    """Result of a single ``docker exec`` invocation via the SDK."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _from_env() -> Any:
    """Single boundary call to ``docker.from_env`` so tests can mock here.

    Returns the docker-py client. Raises :class:`DockerNotAvailableError`
    when the SDK isn't installed or the daemon isn't reachable.
    """
    try:
        import docker
    except ImportError as exc:
        raise DockerNotAvailableError(
            "docker-py is not installed. "
            "Install the [docker-clean] extra: "
            "`pip install shimkit[docker-clean]` or "
            "`uv tool install shimkit[docker-clean]`."
        ) from exc
    try:
        client = docker.from_env(timeout=10)
        client.ping()
    except Exception as exc:
        raise DockerNotAvailableError(
            f"Docker daemon is not reachable: {exc}. "
            "Is Docker Desktop running? On Linux, are you in the "
            "`docker` group?"
        ) from exc
    return client


class DockerEnv:
    """Owns the docker-py client + shimkit's container/volume
    naming conventions.

    Built with the same ``create() → boot() → use`` pattern as the
    rest of shimkit's managers. ``boot()`` exits 69 when the SDK
    isn't installed or the daemon is unreachable, so callers can
    treat the post-boot ``DockerEnv`` as a safe-to-use handle.
    """

    def __init__(self) -> None:
        self._client: Any | None = None

    @classmethod
    def create(cls) -> DockerEnv:
        return cls()

    def boot(self) -> DockerEnv:
        """Verify the SDK is present and the daemon is reachable.

        Exits 69 with a clear remediation message on failure. Idempotent
        — repeated calls reuse the same client.
        """
        if self._client is not None:
            return self
        try:
            self._client = _from_env()
        except DockerNotAvailableError as exc:
            UI.error(str(exc))
            sys.exit(EX_UNAVAILABLE)
        return self

    @property
    def client(self) -> Any:
        """The underlying docker-py client. Must call ``boot()`` first."""
        assert self._client is not None, "call boot() first"
        return self._client

    # ─── naming conventions ────────────────────────────────────────

    @staticmethod
    def container_name(scope: str, kind: str, id_: str = "dev") -> str:
        """``shimkit-<scope>-<kind>-<id>``.

        ``scope`` is the top-level subcommand (``db``, ``stack``, ...);
        ``kind`` is the per-engine / per-recipe label (``mysql``,
        ``lemp``, ...); ``id_`` lets one user run several side-by-side
        (default ``dev``).
        """
        return f"shimkit-{scope}-{kind}-{id_}"

    @staticmethod
    def volume_path(engine: str, id_: str = "dev") -> Path:
        """``~/.shimkit/data/db/<engine>-<id>/`` — bind-mount root for
        a single-engine database container.

        The directory is NOT created by this helper; the caller does it
        at ``run()`` time so the conventions module stays I/O-free.
        """
        return Path.home() / ".shimkit" / "data" / "db" / f"{engine}-{id_}"

    # ─── lifecycle (thin SDK wrappers) ─────────────────────────────

    def find(self, name: str) -> Any | None:
        """Return the container object for ``name`` (any state) or
        ``None`` when no such container exists.
        """
        from docker.errors import NotFound

        try:
            return self.client.containers.get(name)
        except NotFound:
            return None

    def run(
        self,
        image: str,
        *,
        name: str,
        env: Mapping[str, str] | None = None,
        ports: Mapping[str, int | tuple[str, int]] | None = None,
        volumes: Mapping[str, Mapping[str, str]] | None = None,
        detach: bool = True,
        labels: Mapping[str, str] | None = None,
        restart_policy: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create + start a new container.

        Shimkit-managed defaults: ``detach=True``; a ``shimkit.tool``
        label set to the scope inferred from ``name`` (the first
        component after ``shimkit-``).
        """
        full_labels = {**(labels or {}), "shimkit.tool": _scope_from(name)}
        return self.client.containers.run(
            image,
            name=name,
            detach=detach,
            environment=dict(env) if env else None,
            ports=dict(ports) if ports else None,
            volumes={k: dict(v) for k, v in volumes.items()} if volumes else None,
            labels=full_labels,
            restart_policy=dict(restart_policy) if restart_policy else None,
            **kwargs,
        )

    def start(self, name: str) -> bool:
        """Start an existing-but-stopped container. Returns False when
        no such container exists.
        """
        c = self.find(name)
        if c is None:
            return False
        c.start()
        return True

    def stop(self, name: str, *, timeout: int = 10) -> bool:
        """Stop a running container. Returns False when no such
        container exists. Returns True when the container exists, even
        if it was already stopped."""
        c = self.find(name)
        if c is None:
            return False
        c.stop(timeout=timeout)
        return True

    def remove(self, name: str, *, force: bool = False) -> bool:
        """Remove a container. Returns False when no such container
        exists.
        """
        c = self.find(name)
        if c is None:
            return False
        c.remove(force=force)
        return True

    def run_oneshot(
        self,
        image: str,
        *,
        command: list[str],
        name: str | None = None,
        env: Mapping[str, str] | None = None,
        volumes: Mapping[str, Mapping[str, str]] | None = None,
        labels: Mapping[str, str] | None = None,
        wait_timeout: int = 600,
    ) -> ExecOutcome:
        """Run a container to completion and return its outcome.

        Detached + waited rather than ``detach=False`` so we get both the
        exit code and demuxed stdout/stderr — `containers.run(detach=False)`
        returns a single bytes blob and raises ContainerError on non-zero
        exit, which is harder to surface cleanly to UI.

        The container is removed on exit (success or failure) so a long
        loop of one-shots doesn't accumulate dead containers. Image-pull
        is implicit — docker-py pulls if the image isn't local.
        """
        from docker.errors import APIError, ImageNotFound

        labels_full = {**(labels or {}), "shimkit.tool": _scope_from(name or "")}
        try:
            c = self.client.containers.run(
                image,
                command=command,
                name=name,
                detach=True,
                environment=dict(env) if env else None,
                volumes={k: dict(v) for k, v in volumes.items()} if volumes else None,
                labels=labels_full,
            )
        except ImageNotFound:
            return ExecOutcome(exit_code=125, stdout="", stderr=f"image not found: {image}")
        except APIError as exc:
            return ExecOutcome(exit_code=125, stdout="", stderr=str(exc))

        try:
            result = c.wait(timeout=wait_timeout)
            exit_code = int(result.get("StatusCode", 1)) if isinstance(result, dict) else 1
            stdout_b = c.logs(stdout=True, stderr=False) or b""
            stderr_b = c.logs(stdout=False, stderr=True) or b""
        finally:
            with contextlib.suppress(APIError):
                c.remove(force=True)

        return ExecOutcome(
            exit_code=exit_code,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
        )

    def exec(
        self,
        name: str,
        cmd: list[str],
        *,
        tty: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> ExecOutcome:
        """``docker exec`` inside ``name``. Returns the outcome."""
        c = self.find(name)
        if c is None:
            return ExecOutcome(
                exit_code=125,  # "no such container"
                stdout="",
                stderr=f"no such container: {name}",
            )
        # exec_run with demux=True returns (stdout, stderr) tuple.
        exit_code, output = c.exec_run(
            cmd,
            tty=tty,
            demux=True,
            environment=dict(environment) if environment else None,
        )
        if isinstance(output, tuple):
            stdout_b, stderr_b = output
        else:
            stdout_b, stderr_b = output, b""
        return ExecOutcome(
            exit_code=int(exit_code or 0),
            stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
            stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
        )

    def logs(self, name: str, *, follow: bool = False, tail: int | None = None) -> Any:
        """Return the container's log stream (or static bytes when
        ``follow=False``). Returns ``None`` when the container doesn't
        exist.
        """
        c = self.find(name)
        if c is None:
            return None
        return c.logs(stream=follow, follow=follow, tail=tail if tail is not None else "all")

    def list_managed(self, *, scope: str | None = None) -> list[Any]:
        """List every container with the ``shimkit.tool`` label, optionally
        narrowed to a specific scope (``"db"``, ``"stack"``, ...).
        """
        filters: dict[str, Any] = {"label": ["shimkit.tool"]}
        if scope is not None:
            filters["label"] = [f"shimkit.tool={scope}"]
        result: list[Any] = self.client.containers.list(all=True, filters=filters)
        return result

    # ─── networks ──────────────────────────────────────────────────

    def network_get_or_create(self, name: str) -> Any:
        """Return the docker network with ``name``, creating it as a
        user-defined bridge if absent. Idempotent.

        Containers attached to a user-defined bridge can resolve each
        other's names via Docker's built-in DNS — which is how shimkit
        stacks let nginx fastcgi-pass to ``shimkit-stack-lemp-<proj>-php``
        without exposing a host port.
        """
        from docker.errors import NotFound

        try:
            return self.client.networks.get(name)
        except NotFound:
            return self.client.networks.create(
                name,
                driver="bridge",
                labels={"shimkit.tool": _scope_from(name)},
            )

    def network_remove(self, name: str) -> bool:
        """Remove the named network. Returns False when absent."""
        from docker.errors import NotFound

        try:
            net = self.client.networks.get(name)
        except NotFound:
            return False
        net.remove()
        return True

    def remove_volume(self, path: Path) -> bool:
        """Remove a bind-mount volume directory created by shimkit.

        Refuses to delete anything outside ``~/.shimkit/data/`` —
        defense-in-depth against caller bugs that pass a stray
        absolute path.
        """
        root = Path.home() / ".shimkit" / "data"
        try:
            path.relative_to(root)
        except ValueError:
            return False
        if not path.exists():
            return False
        import shutil

        shutil.rmtree(path)
        return True


def _scope_from(container_name: str) -> str:
    """``shimkit-db-mysql-dev`` → ``db``. Best-effort; falls back to
    the empty string for names that don't match the convention.
    """
    parts = container_name.split("-")
    if len(parts) >= 2 and parts[0] == "shimkit":
        return parts[1]
    return ""
