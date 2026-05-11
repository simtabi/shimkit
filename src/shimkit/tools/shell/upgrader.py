"""Upgrade bash / zsh / fish / ksh via the host's package manager.

The list of supported shells is config-driven
(``config.tools.shell.supported_shells``). Version detection runs the
shell binary's ``--version`` and parses a semver-like sequence from the
output. Cross-platform: the actual upgrade is delegated to whichever
PackageManager is on the host.
"""

from __future__ import annotations

import re
import shutil

from shimkit.config import get_config
from shimkit.core import CommandRunner, PackageManager, Platform

_SEMVER_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)")


class ShellUpgrader:
    """Detect and upgrade shells through PackageManager."""

    def __init__(self, platform: Platform, pkgmgr: PackageManager) -> None:
        self._platform = platform
        self._pkgmgr = pkgmgr

    @property
    def supported_shells(self) -> list[str]:
        return list(get_config().tools.shell.supported_shells)

    def installed_version(self, name: str) -> str | None:
        """Run ``<shell> --version`` and parse a semver triple."""
        binary = shutil.which(name)
        if not binary:
            return None
        r = CommandRunner.run([binary, "--version"])
        text = (r.stdout + "\n" + r.stderr).strip()
        m = _SEMVER_RE.search(text)
        return m.group(1) if m else None

    def upgrade(self, name: str) -> bool:
        """Run ``<pm> update`` then ``<pm> upgrade <shell>``. Returns True on success."""
        if name not in self.supported_shells:
            return False
        self._pkgmgr.update()
        return self._pkgmgr.upgrade(name).ok

    def simulate(self, name: str) -> str:
        """Return the rendered command shimkit *would* run, without executing."""
        if name not in self.supported_shells:
            return f"[unsupported] {name} is not in tools.shell.supported_shells"
        update = self._pkgmgr.render(self._pkgmgr.template("update"))
        upgrade = self._pkgmgr.render(self._pkgmgr.template("upgrade"), pkg=name)
        return f"[dry-run] {update}\n[dry-run] {upgrade}"
