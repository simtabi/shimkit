"""Docker Desktop lifecycle helpers.

Docker Desktop 4.37+ exposes ``docker desktop status|start|stop|restart``
as a first-class CLI. We probe for it and fall back to the older
``osascript``/``open -a`` path on macOS only when the new command is
absent.
"""

from __future__ import annotations

import shutil
import time

from shimkit.core import CommandRunner, Platform


def has_desktop_cli() -> bool:
    """True iff `docker desktop` is available (Docker Desktop 4.37+)."""
    if shutil.which("docker") is None:
        return False
    r = CommandRunner.run(["docker", "desktop", "--help"])
    return r.ok


def status() -> str:
    """One-line summary of `docker desktop status` or `<no desktop>`."""
    if not has_desktop_cli():
        return "<no desktop CLI>"
    r = CommandRunner.run(["docker", "desktop", "status"])
    if not r.ok:
        return "<unavailable>"
    return r.stdout.strip().splitlines()[0] if r.stdout.strip() else "<empty>"


def restart(platform: Platform | None = None) -> bool:
    """Restart Docker Desktop. Prefers `docker desktop restart`."""
    if has_desktop_cli():
        return CommandRunner.run(["docker", "desktop", "restart"], capture_output=False).ok

    # Fallback only makes sense on macOS where Docker Desktop is a .app.
    plat = platform or Platform.detect()
    if not plat.is_macos:
        return False
    # Best-effort: `osascript -e 'quit app "Docker"'` then `open -a Docker`.
    CommandRunner.run(["osascript", "-e", 'quit app "Docker"'])
    time.sleep(3)
    return CommandRunner.run(["open", "-a", "Docker"]).ok
