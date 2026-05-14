"""Self-update for the shimkit binary itself.

Detects which package manager installed shimkit (uv, pipx, pip, brew)
and dispatches the right upgrade command. The version lookup queries
the PyPI JSON API for ``shimkit``; the GitHub repo from
``config.self_update.github_repo`` is reported in messages but is not
itself downloaded.

Graceful when no install method is detected — prints the direct
install commands so the user can reinstall manually.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Literal
from urllib.request import urlopen

from shimkit import __version__
from shimkit.config import get_config
from shimkit.core import UI, CommandRunner

InstallMethod = Literal["uv", "pipx", "pip", "brew"]

PYPI_JSON_URL = "https://pypi.org/pypi/shimkit/json"


@dataclass(frozen=True)
class UpdateCheckResult:
    current: str
    latest: str | None
    method: InstallMethod | None

    @property
    def has_update(self) -> bool:
        if self.latest is None:
            return False
        return _parse(self.latest) > _parse(self.current)


def _parse(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def _latest_pypi_version() -> str | None:
    """Return the latest shimkit version from PyPI, or None on any error."""
    try:
        # PYPI_JSON_URL is a hardcoded https:// constant — not user-controlled.
        with urlopen(PYPI_JSON_URL, timeout=3) as resp:  # nosec B310
            data = json.load(resp)
        version: str = data["info"]["version"]
        return version
    except Exception:
        return None


def _detect_install_method() -> InstallMethod | None:
    """Detect how the running shimkit was installed.

    Order matters: uv before pipx (uv tools may also be visible to pipx);
    pipx before pip (pipx installs into a venv that pip can also see);
    brew last because the formula could co-exist with a Python install.
    """
    r = CommandRunner.run(["uv", "tool", "list"])
    if r.ok and "shimkit" in r.stdout:
        return "uv"

    r = CommandRunner.run(["pipx", "list", "--short"])
    if r.ok and "shimkit" in r.stdout:
        return "pipx"

    r = CommandRunner.run(["brew", "list", "--formula"])
    if r.ok and "shimkit" in r.stdout:
        return "brew"

    r = CommandRunner.run([sys.executable, "-m", "pip", "show", "shimkit"])
    if r.ok and "Name: shimkit" in r.stdout:
        return "pip"

    return None


_DISPATCH: dict[InstallMethod, list[str]] = {
    "uv": ["uv", "tool", "upgrade", "shimkit"],
    "pipx": ["pipx", "upgrade", "shimkit"],
    "brew": ["brew", "upgrade", "shimkit"],
    # pip rendered at runtime — sys.executable is not stable at module load
}


def _pip_upgrade_cmd() -> list[str]:
    return [sys.executable, "-m", "pip", "install", "--user", "--upgrade", "shimkit"]


def check() -> UpdateCheckResult:
    """Check PyPI for a newer version, plus detect the install method."""
    return UpdateCheckResult(
        current=__version__,
        latest=_latest_pypi_version(),
        method=_detect_install_method(),
    )


def apply(method: InstallMethod) -> bool:
    """Run the upgrade command for the given install method."""
    cmd = _pip_upgrade_cmd() if method == "pip" else _DISPATCH[method]
    UI.dim("$ " + " ".join(cmd))
    r = CommandRunner.run(cmd, capture_output=False)
    return r.ok


def install_commands() -> list[str]:
    """Return the direct install commands for environments where dispatch is impossible."""
    return [
        "uv tool install shimkit",
        "pipx install shimkit",
        "pip install --user shimkit            # Python ≥ 3.10",
        "brew install simtabi/tap/shimkit",
    ]


def run(yes: bool = False) -> int:
    """Top-level entry point wired into ``shimkit self-update``.

    Returns the shell exit code: 0 on success or already-up-to-date,
    1 on upgrade failure, 2 when no install method is detected.
    """
    if not get_config().self_update.enabled:
        UI.info("Self-update is disabled in config.self_update.enabled.")
        return 0

    res = check()

    if res.latest is None:
        UI.warning("Could not reach PyPI to check for updates.")
        return 1

    if not res.has_update:
        UI.success(f"shimkit is already at the latest version ({res.current}).")
        return 0

    UI.info(f"Update available: {res.current} → {res.latest}")

    if res.method is None:
        UI.warning(
            "Could not detect how shimkit was installed (no uv/pipx/brew/pip "
            "match). Reinstall manually with one of:"
        )
        for cmd in install_commands():
            UI.dim(f"  {cmd}")
        return 2

    UI.info(f"Detected install method: {res.method}")

    if not yes:
        from shimkit.core import Menu

        if not Menu.confirm(f"Upgrade shimkit via {res.method}?", default=True):
            UI.info("Cancelled.")
            return 0

    if apply(res.method):
        UI.success(f"shimkit upgraded to {res.latest}.")
        return 0
    UI.error("Upgrade failed.")
    return 1
