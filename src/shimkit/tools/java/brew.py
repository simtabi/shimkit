"""Thin wrapper around Homebrew.

The ``brew --prefix`` query is cached for the lifetime of the instance.
The official install URL is config-driven (``config.brew.install_url``)
so users can pin a release or mirror without forking.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from shimkit.config import get_config
from shimkit.core import UI, CommandResult, CommandRunner, Platform


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
            return [f for f in data.get("formulae", []) if "openjdk" in f.get("name", "")]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def install_self(self) -> bool:
        """Bootstrap Homebrew via the upstream install script.

        The script is downloaded to a tempfile and executed as
        ``/bin/bash <tmp>`` rather than via shell interpolation. This
        avoids any chance of the config-supplied URL injecting shell
        metacharacters, and gives us a clean cleanup path on failure.
        """
        url = get_config().brew.install_url
        if urlparse(url).scheme != "https":
            UI.error(f"Refusing to fetch Homebrew installer from non-HTTPS URL: {url}")
            return False

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".sh", delete=False) as tmp:
                tmp_path = tmp.name
                # urlopen scheme validated above (HTTPS-only).
                with urlopen(url, timeout=30) as resp:  # nosec B310
                    shutil.copyfileobj(resp, tmp)
            os.chmod(tmp_path, 0o700)
            r = CommandRunner.run(["/bin/bash", tmp_path], capture_output=False)
        except Exception as exc:
            UI.error(f"Failed to fetch Homebrew installer: {exc}")
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

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
