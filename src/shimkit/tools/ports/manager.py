"""PortsManager — orchestrator for ``shimkit ports``.

The CommandRunner chokepoint (Rule 2) lives here: ``_list_owners()``
shells out to ``lsof`` on macOS or ``ss`` on Linux and hands the
stdout to a pure parser in :mod:`shimkit.tools.ports.owners`.

UI chokepoint (Rule 5) honoured throughout — no ``print`` /
``typer.echo``; everything routes through ``UI.*`` / ``emit_json``.
"""

from __future__ import annotations

import os
import shutil
import sys

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Menu, Platform, emit_json, get_logger

from . import owners as _owners_mod
from .models import PortOwner

_LOG = get_logger("ports")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69
EX_NOPERM = 77

# Signals we accept on `shimkit ports kill --signal SIGNAL`. Stay
# restrained — the user picked this CLI to stop a stuck dev server,
# not to send SIGUSR1.
_ALLOWED_SIGNALS: frozenset[str] = frozenset({"TERM", "KILL", "INT", "HUP"})


class PortsManager:
    """Orchestrator. Boot picks the platform; commands shell out via CommandRunner."""

    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> PortsManager:
        return cls()

    def boot(self) -> PortsManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                "shimkit ports targets macOS and Linux. "
                f"Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        which = "lsof" if self._platform.is_macos else "ss"
        if shutil.which(which) is None:
            UI.error(
                f"`{which}` is not on PATH. Install it (macOS: "
                "preinstalled; Linux: apt install iproute2 or equivalent) "
                "and retry."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ---- read-only ------------------------------------------------------

    def show(self, *, port: int | None = None, json_out: bool = False) -> int:
        """List listening sockets, optionally narrowed to one port."""
        owners = self.list_owners()
        if port is not None:
            owners = _owners_mod.filter_port(owners, port)

        if json_out:
            emit_json(
                Event(
                    tool="ports",
                    step="show",
                    status="ok",
                    data={
                        "port": port,
                        "owners": [
                            {
                                "port": o.port,
                                "proto": o.proto,
                                "pid": o.pid,
                                "name": o.name,
                                "user": o.user,
                                "address": o.address,
                            }
                            for o in owners
                        ],
                    },
                )
            )
            return EX_OK

        if not owners:
            UI.info(
                f"No listening sockets on port {port}."
                if port is not None
                else "No listening sockets found."
            )
            return EX_OK

        UI.header(f"Listening sockets ({len(owners)})")
        for o in sorted(owners, key=lambda x: (x.port, x.proto, x.pid)):
            UI.line(f"  {o.display}")
        return EX_OK

    # ---- mutating -------------------------------------------------------

    def kill(
        self,
        port: int,
        *,
        signal: str = "TERM",
        dry_run: bool = False,
    ) -> int:
        """Kill every process holding ``port``.

        Caller already gated this behind a MODERATE prompt
        (``--yes`` / ``--force`` / ``--no-input``) for normal-tier
        processes and a SEVERE token for system-tier (pid below
        ``ports.system_pid_threshold`` or pid 1 directly).
        """
        sig = signal.upper().lstrip("-").removeprefix("SIG")
        if sig not in _ALLOWED_SIGNALS:
            UI.error(f"Refusing signal {signal!r}. Allowed: {', '.join(sorted(_ALLOWED_SIGNALS))}.")
            return EX_FAIL

        targets = _owners_mod.filter_port(self.list_owners(), port)
        if not targets:
            UI.info(f"Nothing is holding port {port}.")
            return EX_OK

        cfg = get_config().tools.ports
        threshold = cfg.system_pid_threshold

        UI.header(f"port {port}: {len(targets)} owner(s)")
        for o in targets:
            UI.line(f"  {o.display}")

        for o in targets:
            if o.pid == 1:
                UI.error(
                    "Refusing to signal pid 1 (init). If you really need "
                    f"to, use `--confirm {cfg.init_pid_severe_token}` "
                    "(severe tier)."
                )
                return EX_FAIL

        if dry_run:
            UI.info(f"--dry-run: would send SIG{sig} to {', '.join(str(o.pid) for o in targets)}.")
            return EX_OK

        failed: list[PortOwner] = []
        for o in targets:
            if not self._send_signal(o.pid, sig, low_pid=o.pid <= threshold):
                failed.append(o)
        if failed:
            UI.warning("Could not signal: " + ", ".join(f"{o.name}(pid={o.pid})" for o in failed))
            return EX_FAIL
        UI.success(f"Sent SIG{sig} to {len(targets)} process(es) on port {port}.")
        return EX_OK

    # ---- interactive ---------------------------------------------------

    def run(self) -> None:
        """Bare ``shimkit ports`` interactive menu.

        Free-text input isn't part of the Menu primitive, so the
        interactive menu only exercises read-only paths. For
        ``kill``, point users at the subcommand which can validate the
        port via Typer.
        """
        while True:
            choices = [
                "List all listening sockets",
                "Quit",
            ]
            picked = Menu.select("shimkit ports", choices)
            if picked is None or picked == "Quit":
                return
            if picked == "List all listening sockets":
                self.show()

    # ---- internal -------------------------------------------------------

    def list_owners(self) -> list[PortOwner]:
        """Public for commands.py — read the full set without filtering."""
        assert self._platform is not None, "call boot() first"
        if self._platform.is_macos:
            return self._list_owners_lsof()
        return self._list_owners_ss()

    def _list_owners_lsof(self) -> list[PortOwner]:
        # lsof has odd exit codes: 1 if it finds nothing matching, 0 with
        # results. Don't treat returncode != 0 as fatal.
        r = CommandRunner.run(
            [
                "lsof",
                "-nP",  # numeric, no port-name resolution
                "-iTCP",
                "-sTCP:LISTEN",
                "-iUDP",
                "-F",
                "pcnuP",  # machine-readable: pid, command, name, user, protocol
            ]
        )
        return _owners_mod.parse_lsof(r.stdout)

    def _list_owners_ss(self) -> list[PortOwner]:
        # -t tcp, -u udp, -l listening, -n numeric, -p processes, -H no header
        r = CommandRunner.run(["ss", "-tulnpH"])
        if not r.ok:
            _LOG.warning("ss returned %s; stderr=%r", r.returncode, r.stderr)
            return []
        return _owners_mod.parse_ss(r.stdout)

    def _send_signal(self, pid: int, sig: str, *, low_pid: bool) -> bool:
        """Send signal; surface a clear EX_NOPERM hint if it bounces."""
        r = CommandRunner.run(["kill", f"-{sig}", str(pid)])
        if r.ok:
            return True
        # Non-zero from kill(1) is typically EPERM (not ours) or ESRCH
        # (already gone). ESRCH is fine — treat as success.
        if "no such process" in r.stderr.lower():
            return True
        if low_pid and os.geteuid() != 0:
            UI.warning(
                f"pid {pid} is a system-tier process (below "
                f"threshold); rerun with sudo if you really need it."
            )
        return False
