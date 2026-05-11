"""Cross-platform package manager dispatch.

Detection walks ``config.package_managers.preference_order`` and returns
the first manager whose binary is on PATH and whose ``platforms`` list
includes the current OS. Install/update/upgrade command templates also
come from config — substitution is a single ``${pkg}`` placeholder.

This is the Python port of the dev-tools-utils ``butil_pm_*`` helpers.
"""

from __future__ import annotations

import shutil
from string import Template
from typing import Literal

from shimkit.config import get_config

from .command import CommandResult, CommandRunner, sudo_prefix
from .platform import Platform

TemplateKind = Literal["install", "update", "upgrade"]


class PackageManager:
    """Detected host package manager with templated install/update/upgrade commands."""

    def __init__(
        self,
        name: str,
        install_cmd: str,
        update_cmd: str,
        upgrade_cmd: str,
    ) -> None:
        self.name = name
        self._templates: dict[TemplateKind, str] = {
            "install": install_cmd,
            "update": update_cmd,
            "upgrade": upgrade_cmd,
        }

    @classmethod
    def detect(cls, platform: Platform) -> PackageManager | None:
        """Return the first available, platform-compatible PM from the config order."""
        cfg = get_config().package_managers
        for name in cfg.preference_order:
            entry = cfg.definitions.get(name)
            if entry is None:
                continue
            if platform.os_key not in entry.platforms:
                continue
            if shutil.which(name):
                return cls(
                    name=name,
                    install_cmd=entry.install_cmd,
                    update_cmd=entry.update_cmd,
                    upgrade_cmd=entry.upgrade_cmd,
                )
        return None

    def template(self, kind: TemplateKind) -> str:
        """Return the raw template string for inspection / simulate() rendering."""
        return self._templates[kind]

    def install(self, pkg: str) -> CommandResult:
        return self._run("install", pkg=pkg)

    def upgrade(self, pkg: str) -> CommandResult:
        return self._run("upgrade", pkg=pkg)

    def update(self) -> CommandResult:
        return self._run("update", pkg="")

    def render(self, template: str, *, pkg: str = "") -> str:
        """Render a command template with $pkg substituted."""
        return Template(template).safe_substitute(pkg=pkg)

    def _run(self, kind: TemplateKind, *, pkg: str) -> CommandResult:
        rendered = self.render(self._templates[kind], pkg=pkg)
        sudo = sudo_prefix()
        if sudo:
            rendered = " ".join(sudo) + " " + rendered
        return CommandRunner.run(rendered, shell=True, capture_output=False)
