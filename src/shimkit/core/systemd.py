"""Linux systemd unit helpers.

A small, typed wrapper around the systemctl commands shimkit tools
actually need. Every call routes through :class:`CommandRunner` so
tests can mock at one layer.

Shared between ``shimkit adguard`` and ``shimkit docker-clean``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .command import CommandResult, CommandRunner, sudo_prefix


@dataclass(frozen=True)
class UnitState:
    name: str
    active: bool
    enabled: bool
    exists: bool


class Systemd:
    """Static facade for the subset of systemctl shimkit cares about."""

    @staticmethod
    def is_active(unit: str) -> bool:
        r = CommandRunner.run(["systemctl", "is-active", "--quiet", unit])
        return r.ok

    @staticmethod
    def is_enabled(unit: str) -> bool:
        r = CommandRunner.run(["systemctl", "is-enabled", "--quiet", unit])
        return r.ok

    @staticmethod
    def exists(unit: str) -> bool:
        r = CommandRunner.run(["systemctl", "cat", unit])
        return r.ok

    @classmethod
    def state(cls, unit: str) -> UnitState:
        exists = cls.exists(unit)
        return UnitState(
            name=unit,
            active=cls.is_active(unit) if exists else False,
            enabled=cls.is_enabled(unit) if exists else False,
            exists=exists,
        )

    @staticmethod
    def stop(unit: str) -> CommandResult:
        return CommandRunner.run([*sudo_prefix(), "systemctl", "stop", unit])

    @staticmethod
    def start(unit: str) -> CommandResult:
        return CommandRunner.run([*sudo_prefix(), "systemctl", "start", unit])

    @staticmethod
    def restart(unit: str) -> CommandResult:
        return CommandRunner.run([*sudo_prefix(), "systemctl", "restart", unit])

    @staticmethod
    def disable(unit: str) -> CommandResult:
        return CommandRunner.run([*sudo_prefix(), "systemctl", "disable", unit])

    @staticmethod
    def daemon_reload() -> CommandResult:
        return CommandRunner.run([*sudo_prefix(), "systemctl", "daemon-reload"])

    @staticmethod
    def reload_or_restart(unit: str) -> CommandResult:
        return CommandRunner.run(
            [*sudo_prefix(), "systemctl", "reload-or-restart", unit]
        )

    @staticmethod
    def write_drop_in(
        unit: str,
        name: str,
        body: str,
        *,
        target_dir: str | Path | None = None,
    ) -> Path:
        """Write a systemd drop-in.

        By default the file lands at ``/etc/systemd/<unit>.d/<name>.conf``,
        which is correct for service-unit overrides (``[Service]``,
        ``[Unit]``).

        Some daemons read their configuration from a separate dedicated
        directory rather than from a service-unit drop-in. The canonical
        case is ``systemd-resolved``, whose ``[Resolve]`` section lives
        in ``/etc/systemd/resolved.conf.d/``, not in
        ``/etc/systemd/systemd-resolved.service.d/``. Pass ``target_dir``
        to override the default.

        The drop-in is owned by root, mode 0o644. Caller should call
        :meth:`daemon_reload` and then restart/reload the unit.

        Strategy: write to a user-owned tempfile, then ``sudo install``
        atomically into place. Avoids needing stdin support in
        CommandRunner and keeps every subprocess call routed through
        the chokepoint.
        """
        if not name.endswith(".conf"):
            name = f"{name}.conf"
        target_parent = (
            Path(target_dir) if target_dir is not None else Path(f"/etc/systemd/{unit}.d")
        )
        target = target_parent / name

        CommandRunner.run(
            [*sudo_prefix(), "mkdir", "-p", str(target.parent)],
            capture_output=False,
        )

        fd, tmp = tempfile.mkstemp(prefix="shimkit-dropin-", suffix=".conf")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(body)
            CommandRunner.run(
                [
                    *sudo_prefix(),
                    "install",
                    "-m", "0644",
                    "-o", "root",
                    tmp,
                    str(target),
                ],
                capture_output=False,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)

        return target

    @staticmethod
    def journal(unit: str, lines: int = 80, follow: bool = False) -> CommandResult:
        cmd: list[str] = [
            *sudo_prefix(),
            "journalctl",
            "-u",
            unit,
            "-n",
            str(lines),
        ]
        if follow:
            cmd.append("-f")
        return CommandRunner.run(cmd, capture_output=False)
