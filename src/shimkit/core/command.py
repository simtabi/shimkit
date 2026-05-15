"""Single chokepoint for every subprocess invocation.

No code outside this module calls subprocess directly. Every command goes
through CommandRunner.run() so error handling, output capture, and audit
logging have exactly one place to evolve.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence


class CommandResult:
    """Immutable value object returned by every CommandRunner.run() call."""

    __slots__ = ("returncode", "stderr", "stdout")

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""

    @property
    def ok(self) -> bool:
        """True when the process exited with code 0."""
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Stdout, falling back to stderr — many tools (javac) write to stderr."""
        return self.stdout.strip() if self.stdout.strip() else self.stderr.strip()


class CommandRunner:
    """Static chokepoint. All subprocess invocations route through .run()."""

    @staticmethod
    def run(
        cmd: str | Sequence[str],
        shell: bool = False,
        check: bool = False,
        env: Mapping[str, str] | None = None,
        executable: str | None = None,
        capture_output: bool = True,
        cwd: str | None = None,
    ) -> CommandResult:
        """Execute a command and return a CommandResult.

        Splits a string into argv tokens when shell=False. Catches every
        exception and surfaces it as a failed CommandResult so callers
        never need try/except around command execution.
        """
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()
        try:
            # nosec B602 - this is the chokepoint: callers opt into shell=True
            # explicitly via the `shell` parameter; the security audit lives at
            # each caller site, not here.
            r = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check,
                shell=shell,  # nosec B602
                env=dict(env) if env is not None else None,
                executable=executable,
                cwd=cwd,
            )
            return CommandResult(r.returncode, r.stdout or "", r.stderr or "")
        except subprocess.CalledProcessError as e:
            return CommandResult(e.returncode, e.stdout or "", e.stderr or "")
        except Exception as exc:
            return CommandResult(1, "", str(exc))


def sudo_prefix() -> list[str]:
    """Return ``["sudo"]`` when elevation is needed, ``[]`` otherwise.

    Empty when already root or when sudo is not on PATH, so callers can
    prepend unconditionally without branching on privilege level.
    """
    try:
        if os.geteuid() == 0:
            return []
    except AttributeError:
        # Windows — callers guard before reaching this
        pass
    return ["sudo"] if shutil.which("sudo") else []


def is_root() -> bool:
    """True when the current process is root (UID 0)."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def has_sudo_cached() -> bool:
    """True iff ``sudo -n true`` succeeds — the user has a recent sudo timestamp.

    Used by tools that need root for some operations to surface the
    requirement up-front instead of mid-flight. Tests can monkeypatch
    this directly.
    """
    if is_root():
        return True
    if not shutil.which("sudo"):
        return False
    try:
        r = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=2,
            check=False,
        )
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False
