"""LogsManager — orchestrator for ``shimkit logs``.

Read-only by design. macOS uses ``log show``/``log stream`` (Apple's
Unified Logging — Console.app's data source); Linux uses
``journalctl``. The predicate string is passed through verbatim
because the two systems have different syntaxes:

- macOS: NSPredicate-style, e.g.
  ``process == "kernel" AND subsystem CONTAINS "wifi"``
- Linux journalctl: ``-p err`` for priority, ``-u sshd`` for unit,
  ``--grep PATTERN`` for body regex.

We intentionally don't try to translate between the two — it would
be a leaky abstraction. Surface what each platform's binary accepts.
"""

from __future__ import annotations

import shutil
import sys

from shimkit.config import get_config
from shimkit.core import UI, CommandRunner, Event, Menu, Platform, emit_json, get_logger

_LOG = get_logger("logs")

EX_OK = 0
EX_FAIL = 1
EX_UNAVAILABLE = 69


class LogsManager:
    def __init__(self) -> None:
        self._platform: Platform | None = None

    @classmethod
    def create(cls) -> LogsManager:
        return cls()

    def boot(self) -> LogsManager:
        self._platform = Platform.detect()
        if not (self._platform.is_macos or self._platform.is_linux):
            UI.error(
                f"shimkit logs targets macOS and Linux. Detected platform: {self._platform.system}."
            )
            sys.exit(EX_UNAVAILABLE)
        binary = "log" if self._platform.is_macos else "journalctl"
        if shutil.which(binary) is None:
            UI.error(
                f"`{binary}` not on PATH. macOS: preinstalled. "
                "Linux: install systemd's journalctl (most distros ship it)."
            )
            sys.exit(EX_UNAVAILABLE)
        return self

    # ─── tail ──────────────────────────────────────────────────────────

    def tail(
        self,
        *,
        lines: int | None = None,
        follow: bool = False,
        predicate: str | None = None,
        unit: str | None = None,
        json_out: bool = False,
    ) -> int:
        """Show the most recent N log lines, optionally following."""
        assert self._platform is not None
        cfg = get_config().tools.logs
        n = lines if lines is not None else cfg.default_lines
        if self._platform.is_macos:
            args = ["log", "show", "--last", str(n)]
            if follow:
                # `log stream` doesn't accept --last; use it for follow mode.
                args = ["log", "stream"]
            if predicate:
                args.extend(["--predicate", predicate])
        else:
            args = ["journalctl", "-n", str(n)]
            if follow:
                args.append("-f")
            if unit:
                args.extend(["-u", unit])
            if predicate:
                # Linux: treat predicate as a `--grep` regex.
                args.extend(["--grep", predicate])
        if json_out:
            emit_json(
                Event(
                    tool="logs",
                    step="tail",
                    status="ok",
                    data={
                        "platform": self._platform.system,
                        "args": args,
                        "follow": follow,
                    },
                )
            )
            return EX_OK
        # capture_output=False so streaming output (`-f` / `log stream`)
        # reaches the user's terminal in real time.
        r = CommandRunner.run(args, capture_output=False)
        return EX_OK if r.ok else EX_FAIL

    # ─── grep ──────────────────────────────────────────────────────────

    def grep(
        self,
        pattern: str,
        *,
        since: str | None = None,
        unit: str | None = None,
        json_out: bool = False,
    ) -> int:
        """Search log history for PATTERN."""
        assert self._platform is not None
        cfg = get_config().tools.logs
        if self._platform.is_macos:
            # `log show --predicate 'eventMessage CONTAINS "X"'` matches
            # body text; --last bounds the search window.
            since_arg = since or "1h"
            args = [
                "log",
                "show",
                "--last",
                since_arg,
                "--predicate",
                f'eventMessage CONTAINS "{pattern}"',
            ]
        else:
            since_arg = since or "1 hour ago"
            args = [
                "journalctl",
                "--since",
                since_arg,
                "--grep",
                pattern,
                "-n",
                str(cfg.max_grep_lines),
            ]
            if unit:
                args.extend(["-u", unit])
        if json_out:
            emit_json(
                Event(
                    tool="logs",
                    step="grep",
                    status="ok",
                    data={
                        "platform": self._platform.system,
                        "pattern": pattern,
                        "args": args,
                    },
                )
            )
            return EX_OK
        # journalctl returns 1 when nothing matches; treat that as
        # success since "no hits" isn't an error.
        CommandRunner.run(args, capture_output=False)
        return EX_OK

    # ─── system ────────────────────────────────────────────────────────

    def system_show(
        self,
        *,
        priority: str | None = None,
        lines: int | None = None,
        json_out: bool = False,
    ) -> int:
        """Show recent system log lines filtered by priority/level."""
        assert self._platform is not None
        cfg = get_config().tools.logs
        n = lines if lines is not None else cfg.default_lines
        if self._platform.is_macos:
            # macOS predicate "messageType IN {Error, Fault}" approximates
            # error-and-above. Default = "Default" which is the catch-all.
            pred_map = {
                "error": 'messageType == "error"',
                "fault": 'messageType == "fault"',
                "info": 'messageType == "info"',
                "debug": 'messageType == "debug"',
            }
            args = ["log", "show", "--last", str(n)]
            if priority:
                pred = pred_map.get(priority.lower())
                if pred:
                    args.extend(["--predicate", pred])
        else:
            args = ["journalctl", "-n", str(n)]
            if priority:
                args.extend(["-p", priority])
        if json_out:
            emit_json(
                Event(
                    tool="logs",
                    step="system.show",
                    status="ok",
                    data={
                        "platform": self._platform.system,
                        "priority": priority,
                        "args": args,
                    },
                )
            )
            return EX_OK
        r = CommandRunner.run(args, capture_output=False)
        return EX_OK if r.ok else EX_FAIL

    # ─── interactive ──────────────────────────────────────────────────

    def run(self) -> None:
        while True:
            picked = Menu.select(
                "shimkit logs",
                [
                    "Tail the last 100 lines",
                    "Show recent errors",
                    "Quit",
                ],
            )
            if picked is None or picked == "Quit":
                return
            if picked == "Tail the last 100 lines":
                self.tail()
            elif picked == "Show recent errors":
                self.system_show(priority="error")
