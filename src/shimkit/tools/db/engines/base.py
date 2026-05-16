"""Engine ABC + helpers for the per-engine drivers."""

from __future__ import annotations

from dataclasses import dataclass


class UnsupportedEngineOperationError(RuntimeError):
    """Raised by an engine that doesn't support a given operation
    (e.g. ``phpmyadmin`` doesn't have a shell). Manager catches and
    turns into exit 1 with a friendly message.
    """


@dataclass(frozen=True)
class UpSpec:
    """The complete launch spec for a `db <engine> up` invocation."""

    image: str
    container_name: str
    host_port: int
    container_port: int
    bind_host: str
    environment: dict[str, str]
    volumes: dict[str, dict[str, str]]
    extra_hosts: dict[str, str]


class Engine:
    """Per-engine driver. Subclasses override the few methods that
    differ across engines.

    Three classes of method:

    1. ``up_spec(...)`` — builds the full :class:`UpSpec` from runtime
       knobs (port, volume, password). Most engines share the common
       implementation in :meth:`_build_up_spec`; the deviation point is
       :meth:`environment_for_up`, which returns the engine-specific
       env dict.
    2. ``shell_argv`` / ``dump_argv`` — argv inside the container
       for an interactive shell or a dump-to-stdout.
    3. ``supports_*`` — capability flags for engines without a shell
       (``phpmyadmin``) or dump path (also ``phpmyadmin``).
    """

    # Subclass MUST set these. Default port goes in shimkit's config
    # (`tools.db.engines.<engine>.default_port`); the container_port
    # is the engine's actual internal port (3306 for MySQL etc.).
    name: str = ""
    container_port: int = 0

    # ---- environment -----------------------------------------------------

    def environment_for_up(
        self, *, password: str, extras: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Engine-specific env vars for ``docker run -e ...``. The
        ``password`` is the admin/root password the engine should
        initialise with. ``extras`` is the per-engine knob bag
        (e.g. ``--link`` target for phpmyadmin).
        """
        raise NotImplementedError

    def volume_mounts(self, *, volume_root: str | None) -> dict[str, dict[str, str]]:
        """Map host paths → in-container mount specs.

        Override only when the engine has a non-standard data dir.
        Default implementation places ``volume_root`` (when given) at
        the conventional engine data path. Returns an empty dict when
        the caller asked for an ephemeral container (``volume_root`` is
        ``None``).
        """
        if volume_root is None:
            return {}
        return {volume_root: {"bind": self.data_dir(), "mode": "rw"}}

    def data_dir(self) -> str:
        """In-container path where the engine stores persistent data."""
        raise NotImplementedError

    # ---- operations ------------------------------------------------------

    def shell_argv(self, *, password: str) -> list[str]:
        """argv inside the container for an interactive shell."""
        raise UnsupportedEngineOperationError(
            f"engine {self.name!r} does not have an interactive shell"
        )

    def dump_argv(self, *, password: str) -> list[str]:
        """argv inside the container that writes a dump to stdout."""
        raise UnsupportedEngineOperationError(f"engine {self.name!r} does not support `dump`")

    def supports_shell(self) -> bool:
        return True

    def supports_dump(self) -> bool:
        return True

    # ---- knobs the engine accepts at `up` time ---------------------------

    def requires_link(self) -> bool:
        """True iff the engine needs to be told about a sibling
        container (e.g. ``phpmyadmin`` needs a backing DB).
        """
        return False

    def up_command(self, *, password: str) -> list[str] | None:
        """Override the image's default ``CMD``.

        Default is ``None`` — use the image's built-in entrypoint /
        cmd. Engines that need argv-passed config (e.g. Redis's
        ``--requirepass``, which isn't exposed as an env var by the
        official image) override and return the full argv.
        """
        return None

    # ---- --on-host mode -------------------------------------------------

    def supports_on_host(self) -> bool:
        """Whether this engine has a host-install path that `--on-host`
        manages. mongo + phpmyadmin both return False — mongo's host
        packaging is intentionally out of scope; phpmyadmin has no
        host install at all.
        """
        return False

    def host_client_binary(self) -> str:
        """Host-side client binary for `--on-host shell` (e.g. ``mysql``,
        ``psql``). Defaults to the engine name; override when the engine
        and its CLI differ.
        """
        return self.name

    def host_shell_argv(self, *, password: str) -> list[str]:
        """argv for `--on-host shell`. Connects to localhost on the
        default port — same flag shape as the in-container shell, just
        targeting 127.0.0.1 rather than a docker exec.
        """
        raise UnsupportedEngineOperationError(
            f"engine {self.name!r} has no --on-host shell"
        )
