"""Thin wrapper around Homebrew.

The ``brew --prefix`` query is cached for the lifetime of the instance.
The official install URL is config-driven (``config.brew.install_url``)
so users can pin a release or mirror without forking.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from shimkit.config import get_config
from shimkit.core import CommandResult, CommandRunner, Platform


class Brew:
    """All Homebrew operations route through this class."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform
        self._prefix_cache: str | None = None

    @property
    def installed(self) -> bool:
        return shutil.which("brew") is not None

    @property
    def prefix(self) -> str:
        if self._prefix_cache is None:
            r = CommandRunner.run(["brew", "--prefix"])
            self._prefix_cache = r.output if r.ok else self._platform.brew_prefix
        return self._prefix_cache

    def update(self) -> CommandResult:
        return CommandRunner.run(["brew", "update"])

    def install_pkg(self, pkg: str) -> CommandResult:
        return CommandRunner.run(["brew", "install", pkg], capture_output=False)

    def reinstall_pkg(self, pkg: str) -> CommandResult:
        return CommandRunner.run(["brew", "reinstall", pkg], capture_output=False)

    def uninstall_pkg(self, pkg: str) -> CommandResult:
        return CommandRunner.run(["brew", "uninstall", pkg], capture_output=False)

    def upgrade_pkg(self, pkg: str) -> CommandResult:
        return CommandRunner.run(["brew", "upgrade", pkg], capture_output=False)

    def link(self, pkg: str, force: bool = True) -> CommandResult:
        cmd = ["brew", "link", pkg]
        if force:
            cmd.append("--force")
        return CommandRunner.run(cmd, capture_output=False)

    def outdated_java(self) -> list[dict[str, Any]]:
        r = CommandRunner.run(["brew", "outdated", "--json=v2"])
        if not r.ok:
            return []
        try:
            data = json.loads(r.stdout)
            return [
                f for f in data.get("formulae", []) if "openjdk" in f.get("name", "")
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def install_self(self) -> bool:
        """Bootstrap Homebrew via the upstream install script."""
        url = get_config().brew.install_url
        script = f'/bin/bash -c "$(curl -fsSL {url})"'
        r = CommandRunner.run(script, shell=True, capture_output=False)
        if r.ok:
            for prefix_bin in (
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/home/linuxbrew/.linuxbrew/bin",
                str(Path.home() / ".linuxbrew" / "bin"),
            ):
                if Path(prefix_bin, "brew").exists():
                    os.environ["PATH"] = f"{prefix_bin}:{os.environ.get('PATH', '')}"
                    self._prefix_cache = None
                    break
        return r.ok
